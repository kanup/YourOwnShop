import streamlit as st
import tempfile
from pdf_screening import (
    pdf_ingestion,
    query_function,      # (retained for backward compatibility, not used in new flow)
    generate_summary,    # <-- NEW: For generating the document summary
    retrieve_documents,  # <-- NEW: To retrieve docs for answering questions
    generate_response    # <-- NEW: To generate answers based on context
)
import os

# ===== New: Custom CSS for improved UI styling (mimics ChatGPT look) =====
st.markdown("""
    <style>
    .chat-container {
        max-height: 500px;
        overflow-y: auto;
        padding: 10px;
        border: 1px solid #ddd;
        border-radius: 5px;
        background-color: #f8f9fa;
    }
    .user-msg {
        background-color: #e0f7fa;
        padding: 10px;
        border-radius: 5px;
        margin: 5px 0;
    }
    .bot-msg {
        background-color: #f1f8e9;
        padding: 10px;
        border-radius: 5px;
        margin: 5px 0;
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

st.set_page_config(page_title="NatWest Chatbot", layout="wide")

# ===== Improved Top Header with NatWest Logo =====
with st.container():
    col1, col2 = st.columns([8, 2])
    with col1:
        st.title("Welcome to Treasury Hackathon PDF Screening!")
    with col2:
        st.image("https://upload.wikimedia.org/wikipedia/en/thumb/e/ea/NatWest_logo.svg/2560px-NatWest_logo.svg.png", width=150)

# ===== Sidebar Options: Clear History & Expected Responses PDF =====
with st.sidebar:
    st.header("Options")
    if st.button("Clear Chat History"):
        st.session_state.messages = []
        st.success("Chat history cleared!")
    
    expected_pdf = st.file_uploader("Upload Expected Responses PDF", type="pdf", key="expected_pdf")
    if expected_pdf is not None:
        try:
            # ---- NEW: Process expected PDF to extract text for accuracy demo ----
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
    if st.button("Process PDF & Generate Index"):
        with st.spinner("Processing PDF..."):
            # ---- CHANGED: Pass the uploaded file to pdf_ingestion() to generate vector DB and text chunks
            vector_db, chunks = pdf_ingestion(pdf_file)
            st.session_state.vector_db = vector_db
            st.session_state.chunks = chunks

            # ---- NEW: Generate a well formatted summary with headings/sub-headings
            summary = generate_summary(chunks)
        st.success("PDF processed, indexed, and summarized!")
        st.markdown("## Document Summary")
        st.markdown(summary, unsafe_allow_html=True)

st.markdown("---")
st.markdown("## Chat Interface")

# ===== Improved Chat History Display (Chat container with styled messages) =====
with st.container():
    st.markdown("<div class='chat-container'>", unsafe_allow_html=True)
    for msg in st.session_state.messages:
        if msg["role"] == "User":
            st.markdown(f"<div class='user-msg'><strong>You:</strong> {msg['content']}</div>", unsafe_allow_html=True)
        else:
            st.markdown(f"<div class='bot-msg'><strong>Bot:</strong> {msg['content']}</div>", unsafe_allow_html=True)
            # ---- NEW: Display sources if available for each bot message
            if "sources" in msg and msg["sources"]:
                st.markdown("<em>Sources:</em>")
                for src in msg["sources"]:
                    st.markdown(f"- {src}")
    st.markdown("</div>", unsafe_allow_html=True)

# ===== Chat Input at the Bottom =====
user_query = st.text_input("Enter your query:", key="chat_input")
if st.button("Ask Question") and user_query:
    if st.session_state.vector_db is None:
        st.error("Please upload and process a PDF first.")
    else:
        # ---- Append user message to chat history
        st.session_state.messages.append({"role": "User", "content": user_query})
        
        # ---- Retrieve relevant documents from the indexed vector DB
        retrieved_docs = retrieve_documents(st.session_state.vector_db, user_query)
        context = "\n".join([doc.page_content for doc in retrieved_docs])
        
        # ---- Generate bot response using retrieved context and user query
        answer = generate_response(context, user_query)
        
        # ---- NEW: Collect source information from retrieved documents
        sources = []
        for doc in retrieved_docs:
            src = doc.metadata.get("source", "Unknown Source")
            snippet = doc.page_content[:100].strip().replace("\n", " ")
            sources.append(f"{src}: {snippet}...")
        
        # ---- NEW: Compute accuracy if expected responses are available
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
        
        # ---- Append bot response (with sources and accuracy) to chat history
        st.session_state.messages.append({"role": "Bot", "content": answer, "sources": sources})
        st.experimental_rerun()  # Rerun to update the chat history display

# ---- Optional: Show an error if no query is entered ----
if not user_query:
    st.info("Please enter a query to proceed.")
