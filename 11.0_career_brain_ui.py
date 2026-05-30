import os
import streamlit as st
import lancedb
import fitz  # PyMuPDF
import docx
from google import genai
from google.genai import types
from PIL import Image
from dotenv import load_dotenv

# --- 1. CONFIGURATION ---
load_dotenv()
STAGING_DIR = os.getenv("STAGING_DIR", "C:/vector_staging")
LANCEDB_PATH = os.path.join(STAGING_DIR, "career_brain_lancedb")

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
EMBEDDING_MODEL = "gemini-embedding-001"
CHAT_MODEL = "gemini-3.5-flash" 

# --- 2. HELPER FUNCTIONS ---
def extract_uploaded_text(uploaded_file):
    text = ""
    ext = os.path.splitext(uploaded_file.name)[1].lower()
    try:
        if ext == '.pdf':
            doc = fitz.open(stream=uploaded_file.read(), filetype="pdf")
            for page in doc:
                text += page.get_text() + "\n"
        elif ext in ['.docx', '.doc']:
            doc = docx.Document(uploaded_file)
            text = "\n".join([p.text for p in doc.paragraphs])
        else:
            text = uploaded_file.read().decode('utf-8', errors='ignore')
    except Exception as e:
        st.error(f"Error reading file {uploaded_file.name}: {e}")
    return text[:15000] 

def query_career_brain(user_query, include_ai_chats, include_emails, file_filter, email_filter, top_k=15):
    response = client.models.embed_content(
        model=EMBEDDING_MODEL,
        contents=user_query
    )
    query_vector = response.embeddings[0].values

    db = lancedb.connect(LANCEDB_PATH)
    tbl = db.open_table("career_vectors")
    
    search_results = tbl.search(query_vector).limit(top_k * 20).to_list()
    
    final_results = []
    for res in search_results:
        text = res["text"]
        header = text.split("]")[0] if "]" in text else text
        
        is_chat = "AI_Chat_Log" in header or ".json" in header or "MyActivity" in header
        is_email = "Sent_Email" in header or ".csv" in header

        if not include_ai_chats and is_chat:
            continue 
        if not include_emails and is_email:
            continue
            
        # THE NEW DUAL METADATA GUILLOTINE
        if is_email:
            if email_filter and email_filter.lower() not in header.lower():
                continue
        else:
            if file_filter and file_filter.lower() not in header.lower():
                continue
            
        final_results.append(text)
        if len(final_results) >= top_k:
            break
            
    return final_results

def format_chat_for_download():
    if not st.session_state.messages:
        return "No chat history to download yet."
    
    transcript = "=== MY CAREER BRAIN TRANSCRIPT ===\n\n"
    for msg in st.session_state.messages:
        role = "USER" if msg["role"] == "user" else "CAREER BRAIN"
        transcript += f"[{role}]:\n{msg['content']}\n\n"
        transcript += "-" * 40 + "\n\n"
    return transcript

# --- 3. STREAMLIT UI ---
st.set_page_config(page_title="My Career Brain", page_icon="icon.png", layout="wide")

if "messages" not in st.session_state:
    st.session_state.messages = []

# --- 4. HEADER LAYOUT ---
col1, col2 = st.columns([1, 15])

with col1:
    st.image("icon.png", width=80)

with col2:
    st.markdown(
        "<h1 style='margin-bottom: 0px; padding-bottom: 0px; margin-top: -15px;'>My Career Brain</h1>", 
        unsafe_allow_html=True
    )
    st.markdown(
        "<p style='margin-top: 0px; font-size: 1.1em;'><b>1.5 TB Footprint • 6K Key Docs • 196K Semantic Blocks • 0 SaaS Wrappers</b></p>", 
        unsafe_allow_html=True
    )

# --- 5. SIDEBAR ---
with st.sidebar:
    st.header("⚙️ Engine Controls")
    
    brain_only = st.toggle("Brain Only (Strict RAG)", value=False)
    
    include_chats = st.toggle("Include AI Chats", value=False)
    include_emails = st.toggle("Include Sent Emails", value=True)
    
    st.divider()
    
    # --- NEW: DUAL FILTERS ---
    file_metadata_filter = st.text_input("📁 File Metadata Filter", placeholder="e.g. placemat, 2024, ACME")
    email_metadata_filter = st.text_input("📧 Email Metadata Filter", placeholder="e.g. observability, john.doe@")
    
    st.divider()
    
    uploaded_files = st.file_uploader(
        "Context Upload", 
        type=['pdf', 'docx', 'txt', 'html', 'htm', 'png', 'jpg', 'jpeg'], 
        accept_multiple_files=True
    )

    st.divider()
    
    chat_transcript = format_chat_for_download()
    st.download_button(
        label="💾 Download Chat History",
        data=chat_transcript,
        file_name="career_brain_transcript.txt",
        mime="text/plain",
        use_container_width=True
    )
    
    if st.button("🗑️ Clear Chat History", use_container_width=True):
        st.session_state.messages = []
        st.rerun()

# --- 6. MAIN CHAT INTERFACE ---
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

if prompt := st.chat_input("Query your professional database..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        with st.spinner("Searching the Career Brain..."):
            
            # Pass both filters to the engine
            retrieved_blocks = query_career_brain(
                prompt, 
                include_chats, 
                include_emails, 
                file_metadata_filter, 
                email_metadata_filter
            )
            context_string = "\n\n---\n\n".join(retrieved_blocks)
            
            uploaded_text_context = ""
            uploaded_images = []
            
            if uploaded_files:
                for file in uploaded_files:
                    ext = os.path.splitext(file.name)[1].lower()
                    st.toast(f"Analyzing {file.name}...")
                    
                    if ext in ['.png', '.jpg', '.jpeg']:
                        uploaded_images.append(Image.open(file))
                    else:
                        doc_text = extract_uploaded_text(file)
                        uploaded_text_context += f"\n\n[USER UPLOADED DOCUMENT: {file.name}]:\n{doc_text}\n\n"

            # --- DYNAMIC PROMPT LOGIC ---
            if brain_only:
                retrieval_rules = """2. Strict Knowledge Retrieval:
            - You are operating in "Brain Only" mode. You MUST answer ONLY using the provided 'Retrieved Career Blocks'.
            - Do not hallucinate, invent projects, or pull in outside general LLM knowledge.
            - If the answer to the user's question is not explicitly contained within the blocks, explicitly state: "I cannot find this in your current database."
            """
            else:
                retrieval_rules = """2. Hybrid Knowledge Retrieval: 
            - For questions about the user's specific projects, career history, or personal files, rely ONLY on the 'Retrieved Career Blocks'. Do not invent personal history.
            - However, you are completely free to use your broader, general LLM world knowledge to answer questions about external entities, software vendors, industry trends, or companies (e.g., answering if a vendor is still in business today).
            - When mixing personal data with external knowledge, make it clear which is which.
            """

            system_prompt = f"""You are an elite Career Archivist and Advisory Copilot. You have access to the user's comprehensive professional database.
            
            INSTRUCTIONS & FORMATTING:
            1. Citing Sources: Do not use bulky headers like "Found Files". Cite sources concisely at the very top of your response. Use separate inline code blocks for the folder path and the file name so the user can easily triple-click the folder path. Format it EXACTLY like this (on one line):
            * **Source:** `C:/vector_staging/2023 Q4 Ally Financial/Data Center Placemat/` `Data Center 3.3.pdf`
            
            {retrieval_rules}
            
            3. Context Uploads: If the user uploads documents or images, act as a strategic advisor. Cross-reference their career blocks against the uploaded context.
            """
        
            master_prompt_text = f"RETRIEVED CAREER BLOCKS:\n{context_string}\n{uploaded_text_context}USER QUESTION:\n{prompt}"

            api_payload = [master_prompt_text]
            if uploaded_images:
                api_payload.extend(uploaded_images)

            try:
                response = client.models.generate_content(
                    model=CHAT_MODEL,
                    contents=api_payload,
                    config=types.GenerateContentConfig(system_instruction=system_prompt)
                )
                
                st.markdown(response.text)
                
                with st.expander("🔍 View Retrieved Database Blocks"):
                    if not retrieved_blocks:
                        st.write("No blocks matched your metadata filter(s).")
                    else:
                        st.write(context_string)
                    
                st.session_state.messages.append({"role": "assistant", "content": response.text})
                
                st.rerun()
                
            except Exception as e:
                st.error(f"API Error: {e}")
