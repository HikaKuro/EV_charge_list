"""
FastAPIサーバー - EV充電器データ収集API
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel
import subprocess
import sys
import os
import logging
import asyncio
import threading
import queue

# ロギング設定
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="EV Charger Data Collection API")

# CORS設定（Reactからのアクセスを許可）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],  # ViteとCreate React Appのデフォルトポート
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def read_root():
    """ルートエンドポイント"""
    return {"message": "EV Charger Data Collection API", "status": "running"}

def run_scraper_process(output_queue):
    """スクレイピングプロセスを実行し、出力をキューに送信"""
    try:
        script_path = os.path.join(os.path.dirname(__file__), "ev_scraper.py")
        logger.info(f"スクレイピングスクリプトを実行します: {script_path}")
        
        # Windows環境でのエンコーディングを取得
        import locale
        system_encoding = locale.getpreferredencoding() or 'utf-8'
        
        # プロセスを開始
        process = subprocess.Popen(
            [sys.executable, "-u", script_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=False,  # バイナリモードで読み取る
            bufsize=0,  # バッファリングなし（バイナリモードでは行バッファリングはサポートされていない）
            cwd=os.path.dirname(__file__)
        )
        
        # リアルタイムで出力を読み取る
        logger.info("プロセスの出力を読み取り開始")
        line_count = 0
        for line_bytes in iter(process.stdout.readline, b''):
            if line_bytes:
                line_count += 1
                # 複数のエンコーディングを試す
                line_decoded = None
                for encoding in ['utf-8', system_encoding, 'cp932', 'shift_jis']:
                    try:
                        line_decoded = line_bytes.decode(encoding)
                        break
                    except (UnicodeDecodeError, LookupError):
                        continue
                
                # すべて失敗した場合はエラー処理付きでデコード
                if line_decoded is None:
                    try:
                        line_decoded = line_bytes.decode('utf-8', errors='replace')
                    except Exception:
                        line_decoded = str(line_bytes)
                
                if line_decoded:
                    cleaned_line = line_decoded.rstrip()
                    if cleaned_line:  # 空行でない場合のみキューに追加
                        logger.debug(f"出力行 {line_count}: {cleaned_line[:50]}")
                        output_queue.put(('output', cleaned_line))
        
        logger.info(f"プロセスの出力読み取り完了。合計 {line_count} 行を処理しました。")
        
        process.wait()
        return_code = process.returncode
        
        if return_code == 0:
            output_queue.put(('success', 'スクレイピングが正常に完了しました'))
        else:
            output_queue.put(('error', f'スクレイピングがエラーで終了しました (リターンコード: {return_code})'))
        
        output_queue.put(('done', str(return_code)))
    except Exception as e:
        import traceback
        error_msg = f'エラーが発生しました: {str(e)}\n{traceback.format_exc()}'
        logger.error(error_msg)
        output_queue.put(('error', error_msg))
        output_queue.put(('done', '1'))

@app.post("/run-scrape")
async def run_scrape():
    """スクレイピングを実行するエンドポイント（SSEでリアルタイム進捗を送信）"""
    async def event_generator():
        output_queue = queue.Queue()
        
        # 最初のメッセージを送信
        yield "data: スクレイピングを開始します...\n\n"
        
        # バックグラウンドスレッドでスクレイピングを実行
        thread = threading.Thread(target=run_scraper_process, args=(output_queue,))
        thread.daemon = True
        thread.start()
        
        try:
            empty_count = 0
            while True:
                try:
                    # キューからメッセージを取得（タイムアウト付き）
                    message_type, message = output_queue.get(timeout=0.5)
                    empty_count = 0
                    
                    logger.info(f"メッセージ受信: {message_type} - {message[:50]}")
                    
                    if message_type == 'done':
                        # 完了メッセージを送信
                        yield f"data: {message}\n\n"
                        break
                    elif message_type == 'success':
                        # 成功メッセージを送信
                        yield f"data: {message}\n\n"
                    elif message_type == 'error':
                        # エラーメッセージを送信
                        yield f"data: エラー: {message}\n\n"
                    else:
                        # 進捗メッセージを送信
                        yield f"data: {message}\n\n"
                except queue.Empty:
                    empty_count += 1
                    # タイムアウト時はハートビートを送信（最初の数回のみ）
                    if empty_count <= 3:
                        yield ": heartbeat\n\n"
                    
                    # スレッドが終了しているか確認
                    if not thread.is_alive():
                        logger.info("スレッドが終了しました。残りのメッセージを確認します...")
                        # スレッドが終了しているが、doneメッセージが来ていない場合
                        # 最後のメッセージを待つ
                        try:
                            message_type, message = output_queue.get(timeout=0.5)
                            logger.info(f"最後のメッセージ: {message_type} - {message[:50]}")
                            if message_type == 'done':
                                yield f"data: {message}\n\n"
                            break
                        except queue.Empty:
                            logger.info("キューが空です。終了します。")
                            break
                    continue
        except Exception as e:
            logger.error(f"イベントジェネレーターエラー: {str(e)}")
            yield f"data: エラー: {str(e)}\n\n"
        finally:
            # スレッドの終了を待つ
            thread.join(timeout=5)
            logger.info("イベントジェネレーター終了")
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )

@app.get("/health")
def health_check():
    """ヘルスチェックエンドポイント"""
    return {"status": "healthy"}

class GeocodeRequest(BaseModel):
    address: str

@app.post("/geocode")
async def geocode_address(request: GeocodeRequest):
    """住所を緯度・経度に変換するエンドポイント"""
    try:
        import requests as req
        # OpenStreetMap Nominatim APIを使用（無料）
        url = "https://nominatim.openstreetmap.org/search"
        params = {
            "q": request.address,
            "format": "json",
            "limit": 1,
            "countrycodes": "jp"  # 日本に限定
        }
        headers = {
            "User-Agent": "EV-Charger-Dashboard/1.0"
        }
        
        response = req.get(url, params=params, headers=headers, timeout=10)
        response.raise_for_status()
        
        data = response.json()
        if data and len(data) > 0:
            result = data[0]
            return {
                "success": True,
                "lat": float(result["lat"]),
                "lon": float(result["lon"]),
                "display_name": result.get("display_name", request.address)
            }
        else:
            return {
                "success": False,
                "error": "住所が見つかりませんでした"
            }
    except Exception as e:
        logger.error(f"ジオコーディングエラー: {str(e)}")
        return {
            "success": False,
            "error": str(e)
        }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
