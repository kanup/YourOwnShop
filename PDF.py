import os
import time
from dotenv import load_dotenv
import httpx
from langchain_community.document_loaders import PyPDFLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_openai import AzureOpenAIEmbeddings
from langchain_community.vectorstores import FAISS
from langchain.prompts import PromptTemplate
from langchain_core.prompts import ChatPromptTemplate
from langchain_community.chat_models import ChatOpenAI
from langchain_core.output_parsers import StrOutputParser
from langchain_openai import AzureChatOpenAI
import pprint

load_dotenv()

REQUEST_TIMEOUT_DEFAULT = 1000
TEMPERATURE_DEFAULT = 0.4
CHUNK_SIZE_DEFAULT = 800
CHUNK_OVERLAP_DEFAULT = 20
BATCH_SIZE = 40

API_KEY = os.getenv("OPENAI_API_KEY")
GPT_DEPLOYMENT_NAME = os.getenv("OPENAI_GPT_DEPLOYMENT_NAME")
GPT_AZURE_ENDPOINT = os.getenv("OPENAI_CHAT_API_BASE")
EMBEDDING_API_BASE = os.getenv("OPENAI_EMBED_API_BASE")
EMBEDDING_API_VER = os.getenv("OPENAI_EMBED_API_VERSION")
EMBEDDING_DEPLOYMENT_NAME = os.getenv("OPENAI_EMBEDDING_DEPLOYMENT_NAME")

PDF_PATH = "pdf_path\\23.1-Senior-Facilities-Agreement-Ares-Management-Limited-dated-27-November-2023.pdf"

http_client = httpx.Client(verify=False, follow_redirects=True)

openai_embeddings = AzureOpenAIEmbeddings(
    openai_api_key=API_KEY,
    azure_endpoint=EMBEDDING_API_BASE,
    openai_api_version=EMBEDDING_API_VER,
    azure_deployment=EMBEDDING_DEPLOYMENT_NAME,
    http_client=http_client
)

# ===== Modified pdf_ingestion to accept an uploaded file (instead of using a hard-coded PDF path) =====
def pdf_ingestion(pdf_file=None):
    if pdf_file:
        # Assume pdf_file is a file-like object
        loader = PyPDFLoader(pdf_file)
        pdf_content = loader.load()
    else:
        pdf_content = load_pdf(PDF_PATH)
    chunks = split_text(pdf_content)
    vector_db = generate_embeddings(chunks)
    return vector_db, chunks

def load_pdf(pdf_path):
    loader = PyPDFLoader(pdf_path)
    pdf_content = loader.load()
    print('PDF loading is successful')
    return pdf_content

def split_text(pdf_content, chunk_size=CHUNK_SIZE_DEFAULT, chunk_overlap=CHUNK_OVERLAP_DEFAULT):
    txt_splitter = RecursiveCharacterTextSplitter(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    chunks = txt_splitter.split_documents(pdf_content)
    print('Text splitting is completed')
    return chunks

def generate_embeddings(chunks, batch_size=BATCH_SIZE):
    vector_db = None
    first = True
    print(f"Total chunks: {len(chunks)}")

    for i in range(0, len(chunks), batch_size):
        print(f"Processing batch {i} to {i + batch_size}")
        batch_chunks = chunks[i:i + batch_size]

        if first:
            vector_db = FAISS.from_documents(batch_chunks, openai_embeddings)
            first = False
        else:
            vector_db.add_documents(batch_chunks)

        print(f"Batch {i} to {i + batch_size} processed successfully")
        time.sleep(20)  # Optional delay to avoid rate limits

    return vector_db

def retrieve_documents(vector_db, query, k=5, score_threshold=0.5):
    retriever = vector_db.as_retriever(search_type="similarity_score_threshold", 
                                       search_kwargs={"score_threshold": score_threshold, "k": k})
    result = retriever.invoke(query)
    return result

# ===== NEW: generate_summary to produce a well formatted summary with headings/sub-headings =====
def generate_summary(chunks, temperature=0):
    summary_prompt = """
You are an expert summarizer. Summarize the document provided below into a well formatted summary with clear headings and sub-headings.
Document Content:
{content}

Summary:
"""
    chat_prompt_template = ChatPromptTemplate.from_template(summary_prompt)
    model = AzureChatOpenAI(
        deployment_name=GPT_DEPLOYMENT_NAME,
        temperature=temperature,
        openai_api_version="2023-05-15",
        openai_api_type="azure_ad",
        azure_endpoint=GPT_AZURE_ENDPOINT,
        openai_api_key=API_KEY,
        request_timeout=REQUEST_TIMEOUT_DEFAULT,
        streaming=False,
        http_client=http_client
    )
    chatchain = chat_prompt_template | model | StrOutputParser()
    content = "\n".join([chunk.page_content for chunk in chunks])
    summary = chatchain.invoke({"content": content})
    return summary

import os

def generate_response(context, question, temperature=0.4):
    """
    Generate a response using the AzureChatOpenAI model.
    Default values for API key, deployment name, and endpoint are read from environment variables.
    """
    from langchain_core.prompts import ChatPromptTemplate
    from langchain_openai import AzureChatOpenAI
    from langchain_core.output_parsers import StrOutputParser
    
    # Read environment variables (ensure these are set in your environment)
    API_KEY = os.getenv("OPENAI_API_KEY")
    GPT_DEPLOYMENT_NAME = os.getenv("OPENAI_GPT_DEPLOYMENT_NAME")
    GPT_AZURE_ENDPOINT = os.getenv("OPENAI_CHAT_API_BASE")
    REQUEST_TIMEOUT_DEFAULT = 1000  # in milliseconds
    
    sample_prompt_template = """
    You are a helpful assistant that answers questions based on the context provided below.
    Context:
    {context}

    Question: {question}

    Answer (based only on the context above):
    - Provide a detailed answer.
    - Do not mention document IDs or page numbers.
    - If insufficient context is provided, say: "The document does not contain information related to your question. Kindly reframe your question."
    """
    
    chat_prompt_template = ChatPromptTemplate.from_template(sample_prompt_template)
    
    model = AzureChatOpenAI(
        deployment_name=GPT_DEPLOYMENT_NAME,
        temperature=temperature,
        openai_api_version="2023-05-15",
        openai_api_type="azure_ad",
        azure_endpoint=GPT_AZURE_ENDPOINT,
        openai_api_key=API_KEY,
        request_timeout=REQUEST_TIMEOUT_DEFAULT,
        streaming=False
    )
    
    chatchain = chat_prompt_template | model | StrOutputParser()
    response = chatchain.invoke({"context": context, "question": question})
    return response

    
    
    
    


# Original query_function retained for backward compatibility (not used in new UI flow)
def query_function(full_chat_history):
    vector_db, chunks = pdf_ingestion()
    retrieved_docs = retrieve_documents(vector_db, full_chat_history)
    context = "\n".join([doc.page_content for doc in retrieved_docs])
    response = generate_response(context, full_chat_history)
    return response
