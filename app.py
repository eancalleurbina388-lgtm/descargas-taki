import os
import sqlite3
from flask import Flask, render_template, request, send_file, make_response, redirect, url_for
import yt_dlp

app = Flask(__name__)

DOWNLOAD_FOLDER = 'downloads'
if not os.path.exists(DOWNLOAD_FOLDER):
    os.makedirs(DOWNLOAD_FOLDER)

DB_NAME = 'database.db'

def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS pagos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            codigo_operacion TEXT UNIQUE,
            monto TEXT,
            estado TEXT
        )
    ''')
    conn.commit()
    conn.close()

init_db()

@app.route('/', methods=['GET', 'POST'])
def index():
    mensaje = None
    
    # Control de cookies para las 5 descargas gratuitas
    descargas_realizadas = int(request.cookies.get('descargas_taki_count', 0))
    pase_activo = request.cookies.get('descargas_taki_pase', 'no')
    
    if request.method == 'POST':
        url = request.form.get('url')
        tipo = request.form.get('tipo') # 'video' o 'audio'
        
        # Verificar si superó las 5 descargas y no tiene pase activo
        if descargas_realizadas >= 5 and pase_activo != 'si':
            # Verificar si envió código de pago
            codigo_ingresado = request.form.get('codigo_operacion')
            if codigo_ingresado:
                conn = sqlite3.connect(DB_NAME)
                cursor = conn.cursor()
                cursor.execute('SELECT estado FROM pagos WHERE codigo_operacion = ?', (codigo_ingresado,))
                resultado = cursor.fetchone()
                conn.close()
                
                if resultado and resultado[0] == 'APROBADO':
                    # Pase aprobado, permitimos descarga y activamos cookie de pase
                    response = procesar_descarga(url, tipo, descargas_realizadas, pase_activo)
                    response.set_cookie('descargas_taki_pase', 'si', max_age=30*24*60*60)
                    return response
                else:
                    mensaje = "El código de Yape aún está Pendiente de aprobación o es inválido."
            else:
                mensaje = "Has llegado al límite de 5 descargas gratuitas. Realiza el yapeo para continuar."
            
            return render_template('index.html', mensaje=mensaje, descargas=descargas_realizadas, bloquear=True)

        return procesar_descarga(url, tipo, descargas_realizadas, pase_activo)

    bloquear = True if (descargas_realizadas >= 5 and pase_activo != 'si') else False
    return render_template('index.html', mensaje=mensaje, descargas=descargas_realizadas, bloquear=bloquear)

def procesar_descarga(url, tipo, descargas_realizadas, pase_activo):
    try:
        # Opciones avanzadas y clientes alternativos para evitar bloqueos antibot de YouTube
        common_opts = {
            'quiet': True,
            'no_warnings': True,
            'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'extractor_args': {
                'youtube': {
                    'player_client': ['android', 'web', 'ios']
                }
            }
        }

        if tipo == "audio":
            ydl_opts = {
                **common_opts,
                'format': 'bestaudio/best',
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '192',
                }],
                'outtmpl': os.path.join(DOWNLOAD_FOLDER, '%(title)s.%(ext)s'),
            }
        else:
            ydl_opts = {
                **common_opts,
                'format': 'best[ext=mp4]/best',
                'outtmpl': os.path.join(DOWNLOAD_FOLDER, '%(title)s.%(ext)s'),
            }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            file_path = ydl.prepare_filename(info)
            if tipo == "audio":
                file_path = os.path.splitext(file_path)[0] + ".mp3"

        response = make_response(send_file(file_path, as_attachment=True))
        
        # Incrementar contador de cookies si no tiene pase activo
        if pase_activo != 'si':
            nueva_cantidad = descargas_realizadas + 1
            response.set_cookie('descargas_taki_count', str(nueva_cantidad), max_age=30*24*60*60)
            
        return response

    except Exception as e:
        error_msg = f"Error al procesar: {str(e)}"
        return render_template('index.html', mensaje=error_msg, descargas=descargas_realizadas, bloquear=False)

@app.route('/enviar_pago', methods=['POST'])
def enviar_pago():
    codigo = request.form.get('codigo')
    monto = request.form.get('monto')
    
    if codigo and monto:
        try:
            conn = sqlite3.connect(DB_NAME)
            cursor = conn.cursor()
            cursor.execute('INSERT INTO pagos (codigo_operacion, monto, estado) VALUES (?, ?, ?)', (codigo, monto, 'PENDIENTE'))
            conn.commit()
            conn.close()
        except sqlite3.IntegrityError:
            pass # El código ya fue registrado antes
            
    return redirect(url_for('index'))

@app.route('/admin', methods=['GET', 'POST'])
def admin():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    if request.method == 'POST':
        pago_id = request.form.get('pago_id')
        accion = request.form.get('accion') # 'aprobar' o 'eliminar'
        
        if accion == 'aprobar':
            cursor.execute('UPDATE pagos SET estado = "APROBADO" WHERE id = ?', (pago_id,))
        elif accion == 'eliminar':
            cursor.execute('DELETE FROM pagos WHERE id = ?', (pago_id,))
            
        conn.commit()
        
    cursor.execute('SELECT id, codigo_operacion, monto, estado FROM pagos')
    pagos = cursor.fetchall()
    conn.close()
    
    return render_template('admin.html', pagos=pagos)

if __name__ == '__main__':
    app.run(debug=True)