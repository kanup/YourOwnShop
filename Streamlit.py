import streamlit as st
import tempfile
import io
import hashlib  # <-- NEW: for computing file hash
import time    # <-- NEW: to measure processing time (optional)
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

# ===== Updated Custom CSS for a cleaner, ChatGPT-like UI =====
st.markdown("""
    <style>
    /* Container for the header */
    .header-container {
        display: flex;
        justify-content: space-between;
        align-items: center;
        padding-bottom: 10px;
        border-bottom: 1px solid #ddd;
        margin-bottom: 20px;
    }
    /* Chat history container styling */
    .chat-container {
        height: 450px;
        overflow-y: auto;
        padding: 10px;
        border: 1px solid #ddd;
        border-radius: 5px;
        background-color: #f8f9fa;
    }
    /* Chat bubbles */
    .user-msg {
        background-color: #e0f7fa;
        padding: 10px;
        border-radius: 10px;
        margin: 5px 0;
        text-align: right;
    }
    .bot-msg {
        background-color: #f1f8e9;
        padding: 10px;
        border-radius: 10px;
        margin: 5px 0;
        text-align: left;
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
    st.session_state.uploaded_pdf_hash = None  # <-- NEW: for file deduplication

# ===== Header with NatWest Logo =====
with st.container():
    st.markdown("<div class='header-container'>", unsafe_allow_html=True)
    st.markdown("<h1>Welcome to Treasury Hackathon PDF Screening!</h1>", unsafe_allow_html=True)
    st.image("https://upload.wikimedia.org/wikipedia/en/thumb/e/ea/NatWest_logo.svg/2560px-NatWest_logo.svg.png", width=150)
    st.markdown("</div>", unsafe_allow_html=True)

# ===== Sidebar Options =====
with st.sidebar:
    st.header("Options")
    if st.button("Clear Chat History"):
        st.session_state.messages = []
        st.success("Chat history cleared!")
    
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

# ===== Main Area: PDF Upload, Indexing, and Summary Generation =====
st.markdown("## Upload and Index PDF Document")
pdf_file = st.file_uploader("Upload a PDF file", type="pdf", key="pdf_upload")
if pdf_file is not None:
    # ---- NEW: Compute file hash from uploaded file bytes to check for duplicates
    file_bytes = pdf_file.getvalue()
    pdf_hash = hashlib.sha256(file_bytes).hexdigest()

    # ---- Check if the uploaded file is the same as before
    if st.session_state.uploaded_pdf_hash == pdf_hash and st.session_state.vector_db is not None:
        st.info("Same file detected. Reusing existing index.")
        vector_db = st.session_state.vector_db
        chunks = st.session_state.chunks
    else:
        if st.button("Process PDF & Generate Index"):
            with st.spinner("Processing PDF..."):
                start_time = time.time()  # <-- NEW: Start timer for metrics
                # ---- Write uploaded file to a temporary file for processing
                with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
                    tmp.write(file_bytes)
                    tmp_path = tmp.name
                # ---- Process the temporary file instead of a fixed path
                vector_db, chunks = pdf_ingestion(tmp_path)
                st.session_state.vector_db = vector_db
                st.session_state.chunks = chunks
                st.session_state.uploaded_pdf_hash = pdf_hash  # Save the hash for future comparisons
                processing_time = time.time() - start_time  # <-- NEW: Compute processing time
                # ---- Generate a well formatted summary with headings/sub-headings
                summary = generate_summary(chunks)
            st.success("PDF processed, indexed, and summarized!")
            st.markdown("## Document Summary")
            st.markdown(summary, unsafe_allow_html=True)
            # ---- NEW: Display simple metrics below the summary
            st.markdown(f"**Metrics:** Total chunks generated: {len(chunks)} | Processing time: {processing_time:.2f} seconds")
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

# ===== Chat Input Area at the Bottom =====
with st.container():
    st.markdown("<div class='chat-input-container'>", unsafe_allow_html=True)
    user_query = st.text_input("Enter your query:", key="chat_input")
    if st.button("Ask Question"):
        if not user_query:
            st.info("Please enter a query to proceed.")
        elif st.session_state.vector_db is None:
            st.error("Please upload and process a PDF first.")
        else:
            # Append user message to chat history
            st.session_state.messages.append({"role": "User", "content": user_query})
            
            # Retrieve relevant documents from the indexed vector DB
            retrieved_docs = retrieve_documents(st.session_state.vector_db, user_query)
            context = "\n".join([doc.page_content for doc in retrieved_docs])
            
            # Generate bot response using retrieved context and user query
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
