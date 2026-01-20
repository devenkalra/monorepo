import os
import json
import glob
import numpy as np
from google import genai

from PIL import Image, ExifTags
from datetime import datetime
import email
import mimetypes
import docx
from sklearn.metrics.pairwise import cosine_similarity


class SmartIndexer:
    def __init__(self, api_key, documents_dir='./documents', index_file='index_data.json', enable_nlp_querying=True):
        self.api_key = api_key
        self.client = genai.Client(api_key=self.api_key)
        #genai.configure(api_key=self.api_key)
        self.documents_dir = documents_dir
        self.index_file = index_file
        self.index = {}
        self.enable_nlp_querying = enable_nlp_querying
        self.text_model = 'gemini-2.5-flash'
        self.embedding_model = 'text-embedding-004'
        self.allowed_extensions = {
            '.txt', '.pdf', '.docx', '.eml', '.md', '.jpg', '.jpeg', '.png', '.py', '.json'
        }
        self.load_index()

    def _get_file_timestamps(self, filepath):
        try:
            creation_timestamp = os.path.getctime(filepath)
            modification_timestamp = os.path.getmtime(filepath)
            return datetime.fromtimestamp(creation_timestamp).isoformat(), \
                datetime.fromtimestamp(modification_timestamp).isoformat()
        except OSError:
            return None, None

    def _extract_text_from_pdf(self, filepath):
        try:
            import pypdf
            reader = pypdf.PdfReader(filepath)
            text = ""
            for page in reader.pages:
                text += page.extract_text() or ""
            return text
        except ImportError:
            print("Warning: pypdf not installed. Cannot process PDF files.")
            return None
        except Exception as e:
            print(f"Error reading PDF {filepath}: {e}")
            return None

    def _extract_text_from_docx(self, filepath):
        try:
            doc = docx.Document(filepath)
            full_text = []
            for para in doc.paragraphs:
                full_text.append(para.text)
            return '\n'.join(full_text)
        except Exception as e:
            print(f"Error reading DOCX {filepath}: {e}")
            return None

    def _extract_text_from_eml(self, filepath):
        try:
            with open(filepath, 'rb') as f:
                msg = email.message_from_bytes(f.read())

            subject = msg['subject']
            from_addr = msg['from']
            to_addr = msg['to']
            date = msg['date']

            body = ""
            if msg.is_multipart():
                for part in msg.walk():
                    ctype = part.get_content_type()
                    cdispo = str(part.get('Content-Disposition'))
                    if ctype == 'text/plain' and 'attachment' not in cdispo:
                        try:
                            body = part.get_payload(decode=True).decode('utf-8', errors='ignore')
                            break
                        except Exception:
                            pass
            else:
                try:
                    body = msg.get_payload(decode=True).decode('utf-8', errors='ignore')
                except Exception:
                    pass
            return {
                'subject': subject,
                'from': from_addr,
                'to': to_addr,
                'date': date,
                'body': body
            }
        except Exception as e:
            print(f"Error reading EML {filepath}: {e}")
            return None

    def _extract_exif_data(self, filepath):
        exif_data = {}
        try:
            with Image.open(filepath) as img:
                info = img._getexif()
                if info:
                    for tag, value in info.items():
                        decoded = ExifTags.TAGS.get(tag, tag)
                        if decoded in ['DateTimeOriginal', 'Model', 'GPSInfo']:
                            if decoded == 'GPSInfo':
                                gps_info = {}
                                for t in value:
                                    sub_decoded = ExifTags.GPSTAGS.get(t, t)
                                    gps_info[sub_decoded] = value[t]
                                exif_data['GPSInfo'] = gps_info
                            else:
                                exif_data[decoded] = value
        except Exception as e:
            print(f"Error extracting EXIF from {filepath}: {e}")
        return exif_data

    def _summarize_image(self, image_file):

        file_path = image_file  # <-- **CHANGE THIS TO YOUR FILE PATH**

        # 2. UPLOAD THE FILE using the Files API
        # This function returns a File object that Gemini can reference.
        # The file is stored for 48 hours.
        print(f"Uploading file: {file_path}...")
        #uploaded_file = self.client.files.upload(
        #    file=file_path
        #)
        uploaded_file = self.client.files.get(name='files/90mfg90ve11f')
        print(f"File uploaded successfully: {uploaded_file.uri}")

        # 3. CONSTRUCT THE PROMPT and CONTENTS LIST
        prompt_text = "Provide a summary of this image. Also, provide the coordinates of all the human faces detected:"
        # The 'contents' argument is now a list of parts (File object and text string)
        contents = [
            uploaded_file,  # The file object (which references the uploaded data)
            prompt_text  # The text prompt
        ]
        response = self.client.models.generate_content(model='gemini-2.5-flash', contents=contents)
        # 4. CALL generate_content with the list
        #model = genai.GenerativeModel(self.text_model)
        #response = model.generate_content(contents)

        # 5. CLEANUP (Optional but recommended)
        # Files are auto-deleted after 48 hours, but you can delete manually.
        #self.client.files.delete(name=uploaded_file.name)
        #print(f"Deleted file: {uploaded_file.name}")

        return response

    def _get_gemini_summary(self, text_content):
        if not text_content or len(text_content.strip()) < 10:
            return None
        try:
            prompt = f"Summarize the following document content in a single, concise sentence:\n\n{text_content[:4000]}"  # Limit input to avoid token limits
            model = genai.GenerativeModel(self.text_model)
            response = model.generate_content(prompt)
            return response.text.strip()
        except Exception as e:
            print(f"Error generating summary: {e}")
            return None

    def _get_gemini_embedding(self, text_content):
        if not self.enable_nlp_querying or not text_content:
            return None
        try:
            result = genai.embed_content(
                model=self.embedding_model,
                content=text_content,
                task_type="SEMANTIC_SIMILARITY"
            )

            return result['embedding']
        except Exception as e:
            print(f"Error generating embedding: {e}")
            return None

    def index_document(self, filepath):
        if filepath in self.index:
            return  # Already indexed

        file_id = os.path.relpath(filepath, self.documents_dir)
        _, ext = os.path.splitext(filepath)
        ext = ext.lower()

        if ext not in self.allowed_extensions:
            return

        print(f"Indexing: {filepath}")
        metadata = {
            'filepath': filepath,
            'extension': ext,
            'creation_time': None,
            'modification_time': None,
            'summary': None,
            'embedding': None,
            'additional_metadata': {}
        }

        creation_time, modification_time = self._get_file_timestamps(filepath)
        metadata['creation_time'] = creation_time
        metadata['modification_time'] = modification_time

        text_content = None

        if ext == '.txt' or ext == '.md' or ext == '.py' or ext == '.json':
            try:
                with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                    text_content = f.read()
            except Exception as e:
                print(f"Error reading text file {filepath}: {e}")
        elif ext == '.pdf':
            text_content = self._extract_text_from_pdf(filepath)
        elif ext == '.docx':
            text_content = self._extract_text_from_docx(filepath)
        elif ext == '.eml':
            eml_data = self._extract_text_from_eml(filepath)
            if eml_data:
                metadata['additional_metadata'] = {
                    'subject': eml_data['subject'],
                    'from': eml_data['from'],
                    'to': eml_data['to'],
                    'date': eml_data['date']
                }
                text_content = f"Subject: {eml_data['subject']}\nFrom: {eml_data['from']}\nTo: {eml_data['to']}\nDate: {eml_data['date']}\n\n{eml_data['body']}"
        elif ext in ['.jpg', '.jpeg', '.png']:
            exif_data = self._extract_exif_data(filepath)
            if exif_data:
                metadata['additional_metadata']['exif'] = exif_data
            text_content = f"Image file: {os.path.basename(filepath)}. EXIF data: {json.dumps(exif_data)}"
            response = self._summarize_image(filepath)

        if text_content:
            metadata['summary'] = self._get_gemini_summary(text_content)
            if self.enable_nlp_querying:
                metadata['embedding'] = self._get_gemini_embedding(text_content)

        self.index[file_id] = metadata

    def index_directory(self):
        if not os.path.exists(self.documents_dir):
            os.makedirs(self.documents_dir)
            print(f"Created directory: {self.documents_dir}")
            return

        for root, _, files in os.walk(self.documents_dir):
            for file in files:
                filepath = os.path.join(root, file)
                self.index_document(filepath)

    def save_index(self):
        with open(self.index_file, 'w', encoding='utf-8') as f:
            json.dump(self.index, f, indent=4)
        print(f"Index saved to {self.index_file}")

    def load_index(self):
        if os.path.exists(self.index_file):
            with open(self.index_file, 'r', encoding='utf-8') as f:
                self.index = json.load(f)
            print(f"Index loaded from {self.index_file}")
        else:
            print("No existing index found. Starting fresh.")

    def search(self, query, top_k=5):
        if not self.enable_nlp_querying:
            print("NLP querying is disabled. Cannot perform semantic search.")
            return []

        query_embedding = self._get_gemini_embedding(query)
        if query_embedding is None:
            print("Could not generate embedding for the query.")
            return []

        query_embedding_np = np.array(query_embedding).reshape(1, -1)

        results = []
        for file_id, doc_data in self.index.items():
            if doc_data.get('embedding'):
                doc_embedding_np = np.array(doc_data['embedding']).reshape(1, -1)
                similarity = cosine_similarity(query_embedding_np, doc_embedding_np)[0][0]
                results.append({
                    'file_id': file_id,
                    'filepath': doc_data['filepath'],
                    'summary': doc_data['summary'],
                    'similarity': similarity,
                    'additional_metadata': doc_data['additional_metadata']
                })

        results.sort(key=lambda x: x['similarity'], reverse=True)
        return results[:top_k]


if __name__ == "__main__":
    # Ensure a 'documents' directory exists for testing
    if not os.path.exists('./documents'):
        os.makedirs('./documents')

    # Create some dummy files for demonstration
    with open('./documents/project_specs.txt', 'w') as f:
        f.write(
            "This document outlines the technical specifications for Project Alpha. It includes requirements for the backend API and frontend UI.")
    with open('./documents/meeting_notes.md', 'w') as f:
        f.write("# Meeting Notes\n- Discussed Q3 budget\n- Action item: Follow up with marketing team.")
    with open('./documents/image_placeholder.jpg', 'w') as f:  # Placeholder, actual image needed for EXIF
        f.write("This is a dummy image file content.")
    with open('./documents/code_example.py', 'w') as f:
        f.write("def calculate_sum(a, b):\n    return a + b\n\n# Main execution block")

    # Get API Key from environment variables
    api_key = os.environ.get('GEMINI_API_KEY') or os.environ.get('API_KEY')
    api_key = "AIzaSyBrU4Xox5GFwSEBSdHeM81yit-8wx_qiQw"
    if not api_key:
        print("Error: GEMINI_API_KEY or API_KEY environment variable not set.")
        print("Please set the environment variable before running the script.")
    else:
        indexer = SmartIndexer(api_key=api_key, documents_dir='/mnt/photo/0 tmp/')

        # Index the target folder
        indexer.index_directory()

        # Save the index
        indexer.save_index()

        # Perform a demo search
        print("\n--- Performing Demo Search ---")
        search_query = "Project specifications"
        print(f"Searching for: '{search_query}'")
        search_results = indexer.search(search_query, top_k=3)

        if search_results:
            print("\nTop search results:")
            for i, result in enumerate(search_results):
                print(f"--- Result {i + 1} ---")
                print(f"File: {result['file_id']}")
                print(f"Similarity: {result['similarity']:.4f}")
                print(f"Summary: {result['summary']}")
                if result['additional_metadata']:
                    print(f"Metadata: {result['additional_metadata']}")
        else:
            print("No relevant documents found or NLP querying is disabled.")

        print("\n--- Performing another Demo Search ---")
        search_query_2 = "Python code examples"
        print(f"Searching for: '{search_query_2}'")
        search_results_2 = indexer.search(search_query_2, top_k=3)

        if search_results_2:
            print("\nTop search results:")
            for i, result in enumerate(search_results_2):
                print(f"--- Result {i + 1} ---")
                print(f"File: {result['file_id']}")
                print(f"Similarity: {result['similarity']:.4f}")
                print(f"Summary: {result['summary']}")
                if result['additional_metadata']:
                    print(f"Metadata: {result['additional_metadata']}")
        else:
            print("No relevant documents found or NLP querying is disabled.")