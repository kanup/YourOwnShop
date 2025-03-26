import streamlit as st
import tempfile
import io
import hashlib  # For computing file hash
import time    # For measuring processing time
from pdf_screening import (
    pdf_ingestion,
    query_function,      # (retained for backward compatibility, not used in new flow)
    generate_summary,
    retrieve_documents,
    generate_response
)
import os

# === IMPORTANT: st.set_page_config must be the very first Streamlit command ===
st.set_page_config(page_title="NatWest Chatbot", layout="wide")

# ===== Updated Custom CSS for a cleaner, ChatGPT-like UI with reduced sizes =====
st.markdown("""
    <style>
    /* Header container styling */
    .header-container {
        display: flex;
        justify-content: space-between;
        align-items: center;
        padding-bottom: 10px;
        border-bottom: 1px solid #ddd;
        margin-bottom: 10px;
    }
    .header-container h1 {
        font-size: 24px; /* Reduced heading size */
        margin: 0;
    }
    /* Chat history container styling */
    .chat-container {
        height: 350px; /* Reduced height */
        overflow-y: auto;
        padding: 10px;
        border: 1px solid #ddd;
        border-radius: 5px;
        background-color: #f8f9fa;
    }
    /* Chat bubbles */
    .user-msg {
        background-color: #e0f7fa;
        padding: 8px;
        border-radius: 10px;
        margin: 5px 0;
        text-align: right;
        font-size: 14px;
    }
    .bot-msg {
        background-color: #f1f8e9;
        padding: 8px;
        border-radius: 10px;
        margin: 5px 0;
        text-align: left;
        font-size: 14px;
    }
    /* Fixed container for chat input */
    .chat-input-container {
        position: sticky;
        bottom: 0;
        background: white;
        padding: 10px 0;
        border-top: 1px solid #ddd;
    }
    </style>
""", unsafe_allow_html=True)

# ===== Session State Initialization =====
if "vector_db" not in st.session_state:
    st.session_state.vector_db = None
if "chunks" not in st.session_state:
    st.session_state.chunks = None
if "messages" not in st.session_state:
    st.session_state.messages = []
if "expected_text" not in st.session_state:
    st.session_state.expected_text = ""
if "uploaded_pdf_hash" not in st.session_state:
    st.session_state.uploaded_pdf_hash = None  # For file deduplication
if "summary" not in st.session_state:
    st.session_state.summary = None
if "processing_time" not in st.session_state:
    st.session_state.processing_time = None

# ===== Header with NatWest Logo (with reduced logo size) =====
with st.container():
    st.markdown("<div class='header-container'>", unsafe_allow_html=True)
    st.markdown("<h1>Welcome to Treasury Hackathon PDF Screening!</h1>", unsafe_allow_html=True)
    st.image("https://upload.wikimedia.org/wikipedia/en/thumb/e/ea/NatWest_logo.svg/2560px-NatWest_logo.svg.png", width=100)  # Reduced logo width
    st.markdown("</div>", unsafe_allow_html=True)

# ===== Sidebar Options: File Uploads for PDF Document and Expected Responses =====
with st.sidebar:
    st.header("Upload Options")
    
    # --- PDF Document Upload for Indexing (in the sidebar) ---
    pdf_file = st.file_uploader("Upload PDF Document", type="pdf", key="pdf_upload")
    if pdf_file is not None:
        # Compute file hash to check for duplicates
        file_bytes = pdf_file.getvalue()
        pdf_hash = hashlib.sha256(file_bytes).hexdigest()
        
        # If the same file was previously processed, reuse the vector index
        if st.session_state.uploaded_pdf_hash == pdf_hash and st.session_state.vector_db is not None:
            st.info("Same file detected. Reusing existing index.")
            vector_db = st.session_state.vector_db
            chunks = st.session_state.chunks
        else:
            if st.button("Process PDF & Generate Index", key="process_pdf"):
                with st.spinner("Processing PDF..."):
                    start_time = time.time()
                    # Write the uploaded file to a temporary file for processing
                    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
                        tmp.write(file_bytes)
                        tmp_path = tmp.name
                    # Process the temporary file (using its path)
                    vector_db, chunks = pdf_ingestion(tmp_path)
                    st.session_state.vector_db = vector_db
                    st.session_state.chunks = chunks
                    st.session_state.uploaded_pdf_hash = pdf_hash
                    processing_time = time.time() - start_time
                    summary = generate_summary(chunks)
                    st.session_state.summary = summary
                    st.session_state.processing_time = processing_time
                st.success("PDF processed, indexed, and summarized!")
    
    # --- Expected Responses PDF Upload (optional) ---
    expected_pdf = st.file_uploader("Upload Expected Responses PDF", type="pdf", key="expected_pdf")
    if expected_pdf is not None:
        try:
            from PyPDF2 import PdfReader
            reader = PdfReader(expected_pdf)
            expected_text = ""
            for page in reader.pages:
                expected_text += page.extract_text() + "\n"
            st.session_state.expected_text = expected_text
            st.success("Expected responses loaded.")
        except Exception as e:
            st.error(f"Error processing expected PDF: {e}")

# ===== Main Area: Document Summary and Chat Interface =====
# --- Display Summary in the Main Area if Available ---
if st.session_state.summary:
    st.markdown("## Document Summary")
    st.markdown(st.session_state.summary, unsafe_allow_html=True)
    st.markdown(f"**Metrics:** Total chunks: {len(st.session_state.chunks)} | Processing time: {st.session_state.processing_time:.2f} seconds")

st.markdown("---")
st.markdown("## Chat Interface")

# ===== Chat History Display =====
with st.container():
    st.markdown("<div class='chat-container'>", unsafe_allow_html=True)
    for msg in st.session_state.messages:
        if msg["role"] == "User":
            st.markdown(f"<div class='user-msg'><strong>You:</strong> {msg['content']}</div>", unsafe_allow_html=True)
        else:
            st.markdown(f"<div class='bot-msg'><strong>Bot:</strong> {msg['content']}</div>", unsafe_allow_html=True)
            # Display sources if available
            if "sources" in msg and msg["sources"]:
                st.markdown("<em>Sources:</em>")
                for src in msg["sources"]:
                    st.markdown(f"- {src}")
    st.markdown("</div>", unsafe_allow_html=True)

# ===== Chat Input Area =====
with st.container():
    st.markdown("<div class='chat-input-container'>", unsafe_allow_html=True)
    user_query = st.text_input("Enter your query:", key="chat_input")
    if st.button("Ask Question"):
        if not user_query:
            st.info("Please enter a query to proceed.")
        elif st.session_state.vector_db is None:
            st.error("Please upload and process a PDF first.")
        else:
            # Append user's query to chat history
            st.session_state.messages.append({"role": "User", "content": user_query})
            # Retrieve relevant documents from the indexed vector DB
            retrieved_docs = retrieve_documents(st.session_state.vector_db, user_query)
            context = "\n".join([doc.page_content for doc in retrieved_docs])
            # Generate the bot's response using the retrieved context and user's query
            answer = generate_response(context, user_query)
            # Collect source information from retrieved documents
            sources = []
            for doc in retrieved_docs:
                src = doc.metadata.get("source", "Unknown Source")
                snippet = doc.page_content[:100].strip().replace("\n", " ")
                sources.append(f"{src}: {snippet}...")
            # Compute accuracy if expected responses are available
            def compute_accuracy(answer, expected_text):
                answer_words = set(answer.split())
                expected_words = set(expected_text.split())
                common_words = answer_words.intersection(expected_words)
                if not expected_words:
                    return 0
                accuracy = len(common_words) / len(expected_words) * 100
                return round(accuracy, 2)
            if st.session_state.expected_text:
                accuracy = compute_accuracy(answer, st.session_state.expected_text)
                answer += f"\n\nAccuracy compared to expected response: {accuracy}%"
            # Append bot response (with sources and accuracy) to chat history
            st.session_state.messages.append({"role": "Bot", "content": answer, "sources": sources})
            st.experimental_rerun()
    st.markdown("</div>", unsafe_allow_html=True)
