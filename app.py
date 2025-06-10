# /tiktok-uploader/app.py

import os
import io
import requests
import sys
import json
import time
import math
from flask import Flask, request, jsonify

from google.oauth2 import credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from googleapiclient.errors import HttpError

app = Flask(__name__)

TIKTOK_API_BASE_URL = "https://open.tiktokapis.com/v2/"
CHUNK_UPLOAD_SIZE = 5 * 1024 * 1024  # 5 MiB

@app.route('/publish', methods=['POST'])
def publish_endpoint():
    data = request.get_json()
    if not data: return jsonify({"error": "Corpo da requisição ausente."}), 400
        
    required_fields = ['tiktok_access_token', 'google_access_token', 'google_file_id', 'title']
    missing_fields = [field for field in required_fields if field not in data]
    if missing_fields: return jsonify({"error": "Campos obrigatórios ausentes.", "missing": missing_fields}), 400

    print(f"\n--- Iniciando publicação para o arquivo ID: {data['google_file_id']} ---")

    try:
        # --- PASSO 1: Obter Metadados ---
        print("[1/4] Obtendo metadados do Google Drive...")
        creds_google = credentials.Credentials(token=data['google_access_token'])
        drive_service = build('drive', 'v3', credentials=creds_google, cache_discovery=False)
        
        metadata = drive_service.files().get(fileId=data['google_file_id'], fields='name, size').execute()
        video_size = int(metadata.get('size', 0))
        if video_size == 0: raise ValueError("Tamanho do arquivo é 0.")
        print(f"--> Tamanho do vídeo: {video_size / (1024*1024):.2f} MB")

        # --- PASSO 2: Iniciar Upload no TikTok ---
        print("[2/4] Iniciando upload no TikTok (init)...")
        total_chunk_count_for_init = int(video_size / CHUNK_UPLOAD_SIZE)
        
        headers_tiktok = {"Authorization": f"Bearer {data['tiktok_access_token']}", "Content-Type": "application/json"}
        payload_init = {
            "post_info": {"title": data['title'], "privacy_level": "SELF_ONLY"},
            "source_info": { "source": "FILE_UPLOAD", "video_size": video_size, "chunk_size": CHUNK_UPLOAD_SIZE, "total_chunk_count": total_chunk_count_for_init }
        }
        
        init_url = f"{TIKTOK_API_BASE_URL}post/publish/video/init/"
        init_response = requests.post(init_url, headers=headers_tiktok, json=payload_init)
        init_response.raise_for_status()
        
        init_result = init_response.json()
        if init_result.get("error", {}).get("code") != "ok": raise requests.exceptions.RequestException(f"Erro na inicialização do TikTok: {init_result}")
        
        upload_url = init_result['data']['upload_url']
        publish_id = init_result['data']['publish_id']
        print(f"--> Inicialização bem-sucedida. Publish ID: {publish_id}")

        # --- PASSO 3: Fazer Upload em Pedaços (LÓGICA VENCEDORA) ---
        print("[3/4] Fazendo upload do vídeo em pedaços...")
        request_download = drive_service.files().get_media(fileId=data['google_file_id'])
        fh = io.BytesIO()
        downloader = MediaIoBaseDownload(fh, request_download, chunksize=CHUNK_UPLOAD_SIZE)
        
        bytes_uploaded = 0
        
        for chunk_number in range(1, total_chunk_count_for_init + 1):
            if chunk_number == total_chunk_count_for_init:
                while True: # Lê até o final no último chunk
                    status, done = downloader.next_chunk(num_retries=3)
                    if done: break
            else:
                status, done = downloader.next_chunk(num_retries=3)

            fh.seek(bytes_uploaded)
            chunk_data = fh.read()
            
            chunk_start = bytes_uploaded
            chunk_end = bytes_uploaded + len(chunk_data) - 1
            bytes_uploaded += len(chunk_data)

            upload_headers = {"Content-Type": "video/mp4", "Content-Range": f"bytes {chunk_start}-{chunk_end}/{video_size}"}
            
            print(f"\r--> Enviando... {bytes_uploaded / (1024*1024):.2f} / {video_size / (1024*1024):.2f} MB", end="")
            
            requests.put(upload_url, headers=upload_headers, data=chunk_data).raise_for_status()
            
        print("\n--> Upload de todos os pedaços concluído.")

        # --- PASSO 4: Verificar Status da Publicação ---
        print("[4/4] Verificando status da publicação no TikTok...")
        time.sleep(5)
        
        status_url = f"{TIKTOK_API_BASE_URL}post/publish/status/fetch/"
        status_payload = {"publish_id": publish_id}
        status_response = requests.post(status_url, headers=headers_tiktok, json=status_payload)
        status_response.raise_for_status()
        
        status_result = status_response.json()
        if status_result.get("error", {}).get("code") != "ok": raise requests.exceptions.RequestException(f"Erro ao verificar status no TikTok: {status_result}")
        
        print(f"--- Processo para o ID {publish_id} concluído com sucesso ---")
        return jsonify({"status": "success", "message": "Vídeo publicado com sucesso.", "publish_id": publish_id, "tiktok_status": status_result['data']}), 200

    except Exception as e:
        error_type = type(e).__name__
        error_message = str(e)
        details = ""
        if hasattr(e, 'response') and e.response is not None:
            try: details = e.response.json()
            except json.JSONDecodeError: details = e.response.text
        return jsonify({"error": error_type, "message": error_message, "details": details}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5002)