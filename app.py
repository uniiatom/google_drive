# app.py (VERSÃO ESTÁVEL E FUNCIONAL)
import os
import io
from flask import Flask, request, jsonify

# Libs do Google
from google.oauth2 import credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from googleapiclient.errors import HttpError

# Lib do Backblaze B2
from b2sdk.v2 import *

app = Flask(__name__)

# --- CONFIGURAÇÃO DAS CREDENCIAIS DO BACKBLAZE B2 ---
B2_KEY_ID = os.environ.get('B2_KEY_ID')
B2_APPLICATION_KEY = os.environ.get('B2_APPLICATION_KEY')
B2_BUCKET_NAME = os.environ.get('B2_BUCKET_NAME')

if not all([B2_KEY_ID, B2_APPLICATION_KEY, B2_BUCKET_NAME]):
    raise ValueError("As variáveis de ambiente do Backblaze (B2_KEY_ID, B2_APPLICATION_KEY, B2_BUCKET_NAME) não foram definidas.")

# --- INICIALIZAÇÃO DO CLIENTE DO BACKBLAZE B2 ---
info = InMemoryAccountInfo()
b2_api = B2Api(info)
b2_api.authorize_account("production", B2_KEY_ID, B2_APPLICATION_KEY)
b2_bucket = b2_api.get_bucket_by_name(B2_BUCKET_NAME)


@app.route('/transfer', methods=['POST'])
def transfer_video():
    data = request.get_json()
    if not data or 'file_id' not in data or 'access_token' not in data:
        return jsonify({"error": "Os campos 'file_id' e 'access_token' do Google Drive são obrigatórios."}), 400

    file_id = data['file_id']
    access_token = data['access_token']
    
    try:
        creds = credentials.Credentials(token=access_token)
        drive_service = build('drive', 'v3', credentials=creds)

        print(f"Buscando metadados do arquivo ID: {file_id}")
        file_metadata = drive_service.files().get(fileId=file_id).execute()
        file_name = file_metadata.get('name', f'video_{file_id}.mp4')
        print(f"Iniciando transferência do arquivo: {file_name}")

        request_download = drive_service.files().get_media(fileId=file_id)
        fh = io.BytesIO()
        downloader = MediaIoBaseDownload(fh, request_download)
        
        done = False
        print("Iniciando download do Google Drive...")
        while not done:
            status, done = downloader.next_chunk()
            if status:
                # Este log de progresso do download funciona e podemos mantê-lo
                print(f"Download do Google Drive: {int(status.progress() * 100)}%.")
        
        print("Download do Google Drive concluído.")
        fh.seek(0)

        print(f"Iniciando upload para o bucket '{B2_BUCKET_NAME}' no Backblaze B2...")
        uploaded_file = b2_bucket.upload_bytes(
            data_bytes=fh.getvalue(),
            file_name=file_name
        )
        print("Upload para o Backblaze B2 concluído!")
        
        return jsonify({
            "status": "success",
            "message": f"Arquivo '{file_name}' transferido com sucesso.",
            "b2_file_info": {
                "id": uploaded_file.id_,
                "name": uploaded_file.file_name,
                "size": uploaded_file.size,
                "bucket_id": uploaded_file.bucket_id
            }
        }), 200

    except HttpError as error:
        print(f"Ocorreu um erro na API do Google: {error}")
        return jsonify({"error": f"Erro na API do Google: {error.reason}", "details": str(error)}), 401
    except Exception as e:
        print(f"Ocorreu um erro inesperado: {e}")
        return jsonify({"error": "Ocorreu um erro interno no servidor.", "details": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)