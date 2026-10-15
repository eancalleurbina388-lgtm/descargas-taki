from flask import Flask, render_template, request, send_file, flash, redirect, url_for, make_response
import yt_dlp
import os
import sqlite3

app = Flask(__name__)
app.secret_key = "descargas_taki_secreto_super_seguro"

DOWNLOAD_FOLDER = "downloads"
os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)

# Configurar Base de Datos SQLite para control seguro
def init_db():
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS transacciones (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            codigo_operacion TEXT UNIQUE,
            monto TEXT,
            estado TEXT
        )
    ''')
    conn.commit()
    conn.close()

init_db()

LIMITE_GRATIS = 5

@app.route("/", methods=["GET", "POST"])
def index():
    descargas_realizadas = int(request.cookies.get('descargas_taki_count', 0))
    
    # Verificar si el usuario tiene un pase aprobado en sus cookies
    pase_activo = request.cookies.get('descargas_taki_pase', 'no')
    bloqueado = (descargas_realizadas >= LIMITE_GRATIS) and (pase_activo != 'si')

    if request.method == "POST":
        accion = request.form.get("accion")

        # 1. Usuario envía su número de operación de Yape para revisión
        if accion == "verificar_yape":
            codigo = request.form.get("num_operacion", "").strip()
            monto = request.form.get("monto", "1.00")
            
            if len(codigo) >= 6:
                try:
                    conn = sqlite3.connect('database.db')
                    cursor = conn.cursor()
                    cursor.execute("INSERT INTO transacciones (codigo_operacion, monto, estado) VALUES (?, ?, ?)", 
                                   (codigo, monto, 'PENDIENTE'))
                    conn.commit()
                    conn.close()
                    flash("¡Código registrado! Tu pago está en revisión. Eladio lo aprobará en breve.", "success")
                except sqlite3.IntegrityError:
                    flash("Este número de operación ya fue registrado anteriormente.", "error")
            else:
                flash("Número de operación inválido. Debe tener al menos 6 dígitos.", "error")
            return redirect(url_for("index"))

        # 2. Procesar descarga (Video o Audio)
        if bloqueado:
            flash("Has alcanzado tu límite. Realiza tu Yape y registra tu código para continuar.", "limit")
            return redirect(url_for("index"))

        url = request.form.get("url")
        tipo = request.form.get("tipo", "video")

        if not url:
            flash("Por favor, ingresa un enlace válido.", "error")
            return redirect(url_for("index"))

        try:
            if tipo == "audio":
                ydl_opts = {
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
                    'format': 'best[ext=mp4]/best',
                    'outtmpl': os.path.join(DOWNLOAD_FOLDER, '%(title)s.%(ext)s'),
                }

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                file_path = ydl.prepare_filename(info)
                if tipo == "audio":
                    file_path = os.path.splitext(file_path)[0] + ".mp3"

            response = make_response(send_file(file_path, as_attachment=True))
            # Si tiene pase activo no sumamos contador, si es gratis sumamos
            if pase_activo != 'si':
                nueva_cantidad = descargas_realizadas + 1
                response.set_cookie('descargas_taki_count', str(nueva_cantidad), max_age=30*24*60*60)
            return response

        except Exception as e:
            flash(f"Error al procesar: {str(e)}", "error")
            return redirect(url_for("index"))

    return render_template("index.html", descargas=descargas_realizadas, limite=LIMITE_GRATIS, bloqueado=bloqueado, pase=pase_activo)

# --- PANEL DE ADMINISTRACIÓN PRIVADO PARA ELADIO ---
@app.route("/admin", methods=["GET", "POST"])
def admin():
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()

    if request.method == "POST":
        op_id = request.form.get("op_id")
        accion_admin = request.form.get("accion_admin")

        if accion_admin == "aprobar":
            cursor.execute("UPDATE transacciones SET estado = 'APROBADO' WHERE id = ?", (op_id,))
        elif accion_admin == "eliminar":
            cursor.execute("DELETE FROM transacciones WHERE id = ?", (op_id,))
        conn.commit()

    cursor.execute("SELECT id, codigo_operacion, monto, estado FROM transacciones ORDER BY id DESC")
    pagos = cursor.fetchall()
    conn.close()

    return render_template("admin.html", pagos=pagos)

# --- RUTA PARA DAR ACCESO AL USUARIO (Simulación de desbloqueo aprobado) ---
@app.route("/revisar-acceso/<codigo>")
def revisar_acceso(codigo):
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    cursor.execute("SELECT estado FROM transacciones WHERE codigo_operacion = ?", (codigo,))
    resultado = cursor.fetchone()
    conn.close()

    if resultado and resultado[0] == 'APROBADO':
        response = make_response(redirect(url_for("index")))
        response.set_cookie('descargas_taki_pase', 'si', max_age=7*24*60*60) # Pase por 7 días
        flash("¡Pago verificado por Eladio! Tienes acceso ilimitado desbloqueado.", "success")
        return response
    else:
        flash("Tu código aún no ha sido aprobado o no existe.", "error")
        return redirect(url_for("index"))

if __name__ == "__main__":
    app.run(debug=True, port=5000)