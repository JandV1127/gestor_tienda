from flask import Flask, render_template, request, redirect, url_for, session, flash, make_response, jsonify
from flask_mail import Mail, Message
from flask_bcrypt import Bcrypt 
from functools import wraps 
from datetime import datetime, date, timedelta # <-- Añadido timedelta
import mysql.connector 
import csv 
from io import StringIO, BytesIO 
import xlsxwriter 
import pandas as pd
from flask import send_file
from io import BytesIO
import secrets # <-- ¡NECESARIO para generar códigos de recuperación!
import io 
import datetime as dt # Importamos el módulo completo con alias 'dt'
from datetime import date, timedelta # Mantenemos date y timedelta
# -------------------------------------------------------------
# CREAR Y CONFIGURAR LA APLICACIÓN FLASK
# -------------------------------------------------------------
app = Flask(__name__)

# Configuración de Clave Secreta para Sesiones y Mensajes Flash
app.secret_key = 'tu_clave_secreta_aqui_para_la_sesion' # ¡IMPORTANTE! Cambiar esto en producción

# Inicializar Bcrypt
bcrypt = Bcrypt(app) 

# Configuración de FLASK-MAIL
app.config['MAIL_SERVER'] = 'smtp.gmail.com'  # O tu servidor SMTP (ej: smtp.office365.com)
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USE_SSL'] = False
# ATENCIÓN: Reemplaza estas credenciales con las tuyas (usa una "Clave de Aplicación" de Google, no tu contraseña principal)
app.config['MAIL_USERNAME'] = 'gestordetiendanyj@gmail.com'  
app.config['MAIL_PASSWORD'] = 'hune aifx rchr idch' # <--- ¡REEMPLAZAR CON LA CLAVE DE APLICACIÓN!
app.config['MAIL_DEFAULT_SENDER'] = 'Ventas Tienda NYJ <gestordetiendanyj@gmail.com>'

mail = Mail(app)

@app.context_processor
def inject_user():
    return dict(
        usuario_nombre=session.get('usuario_nombre'),
        usuario_rol=session.get('usuario_rol')
    )


# -------------------------------------------------------------
# FILTROS JINJA2
# -------------------------------------------------------------
@app.template_filter('currency_format')
def currency_format(value):
    try:
        value = float(value)
        return f"${value:,.2f}"
    except (ValueError, TypeError):
        return "$0.00"


@app.template_filter('date_format')
def date_format(value):
    """Formatea la fecha."""
    if isinstance(value, datetime) or isinstance(value, date):
        return value.strftime('%Y-%m-%d')
    return value
# -------------------------------------------------------------
# FUNCIÓN DE CONEXIÓN A BD
# -------------------------------------------------------------

def db_connector():
    """
    Establece y devuelve una conexión a la base de datos MySQL.
    """
    try:
        conn = mysql.connector.connect(
            host="localhost",
            user="root",
            password="",
            database="gestor_tienda"
        )
        return conn
    except mysql.connector.Error as err:
        print("Error al conectar a la base de datos:", err)
        return None


def verificar_si_es_primera_compra(cliente_id):
    """
    Retorna True si el cliente está haciendo su primera compra.
    """
    try:
        conn = db_connector()
        if not conn:
            return False

        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM ventas WHERE cliente_id = %s", (cliente_id,))
        cantidad = cursor.fetchone()[0]

        cursor.close()
        conn.close()

        return cantidad == 1  # Primera compra

    except Exception as e:
        print("Error verificando primera compra:", e)
        return False

# -------------------------------------------------------------------
# DECORADOR DE SEGURIDAD
# -------------------------------------------------------------------
def login_required(f):
    """
    Decorador que verifica si el usuario ha iniciado sesión.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('loggedin'):
            flash('Debes iniciar sesión para acceder a esta página.', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def enviar_factura_por_correo(destinatario, venta_id, total, detalles_productos,
                              descuento_aplicado=0.0, es_primera_compra=False, nombre_cliente="Cliente"):


    try:
        COLOR_PRIMARIO = "#4285F4"
        COLOR_SECUNDARIO = "#34A853"

        tabla_detalles = ""

        # DETALLES DE PRODUCTOS
        for detalle in detalles_productos:
            nombre = detalle[0]
            cantidad = int(detalle[1])
            precio_unitario = float(detalle[2])
            subtotal_item = float(detalle[3])

            tabla_detalles += f"""
                <tr>
                    <td style="border: 1px solid #ddd; padding: 10px;">{nombre}</td>
                    <td style="border: 1px solid #ddd; padding: 10px; text-align: center;">{cantidad}</td>
                    <td style="border: 1px solid #ddd; padding: 10px; text-align: right;">${precio_unitario:,.2f}</td>
                    <td style="border: 1px solid #ddd; padding: 10px; text-align: right;">${subtotal_item:,.2f}</td>
                </tr>
            """

        # SUBTOTAL ANTES DE DESCUENTO
        subtotal_original_calculado = sum(float(detalle[3]) for detalle in detalles_productos)
        subtotal_original = subtotal_original_calculado

        if descuento_aplicado > 0.0 and descuento_aplicado < 100:
            try:
                subtotal_original = total / (1 - descuento_aplicado / 100)
            except ZeroDivisionError:
                subtotal_original = total
        elif descuento_aplicado == 100:
            subtotal_original = subtotal_original_calculado

        # --------------------------
        # ⭐ BONO SOLO PARA PRIMERA COMPRA (MEJORADO)
        # --------------------------
        bono_html = ""
        if es_primera_compra:
            bono_html = f"""
            <div style="background-color: #FFF3E0; padding: 20px; border-radius: 8px; 
                        text-align: center; margin-top: 25px; border-left: 6px solid #FF9800;">
                
                <h2 style="color: #E65100; margin: 0;">🎉 ¡Gracias por tu primera compra, {nombre_cliente}! 🎉</h2>

                <p style="color: #444; font-size: 15px; margin-top: 10px;">
                    Para nosotros es un placer darte la bienvenida.  
                    Como regalo especial por confiar en nuestra tienda, te obsequiamos un 
                    <b>BONO DEL 10% DE DESCUENTO</b> para tu próxima compra.
                </p>

                <p style="font-size: 20px; font-weight: bold; margin: 15px auto; 
                          background: #ffffff; padding: 12px; width: fit-content; 
                          border-radius: 8px; border: 2px dashed #FF9800;">
                    Código de descuento: <span style="color:#D84315;">NYJ10</span>
                </p>

                <p style="font-size: 13px; color: #555;">
                    *Este bono es válido por 30 días.  
                    ¡Aprovéchalo en tu próxima compra! 🛒
                </p>
            </div>
            """

        # --------------------------
        # CUERPO COMPLETO DEL CORREO
        # --------------------------
        body_html = f"""
        <html>
        <body style="font-family: Arial;">
            <div style="max-width:600px;margin:auto;background:white;padding:20px;border-radius:10px;">
                <h1 style="color:{COLOR_PRIMARIO};text-align:center;">
                    ¡Gracias por tu compra! (Venta #{venta_id})
                </h1>

                <h3>Hola {nombre_cliente}, aquí está tu factura:</h3>

                <table style="width:100%;border-collapse:collapse;">
                    <thead>
                        <tr style="background:#f4f4f4;">
                            <th style="border:1px solid #ddd;padding:8px;">Producto</th>
                            <th style="border:1px solid #ddd;padding:8px;">Cant.</th>
                            <th style="border:1px solid #ddd;padding:8px;">Precio</th>
                            <th style="border:1px solid #ddd;padding:8px;">Subtotal</th>
                        </tr>
                    </thead>
                    <tbody>
                        {tabla_detalles}
                    </tbody>
                </table>

                <div style="text-align:right;margin-top:20px;">
                    <p>Subtotal: ${subtotal_original:,.2f}</p>
                    <p style="color:red;">Descuento: {descuento_aplicado:.2f}%</p>
                    <h2 style="color:{COLOR_SECUNDARIO};">TOTAL PAGADO: ${total:,.2f}</h2>
                </div>

                {bono_html}

                <p style="text-align:center;margin-top:25px;">Gracias por preferirnos 😊</p>
            </div>
        </body>
        </html>
        """

        msg = Message(
            subject=f"Factura de tu compra (Venta #{venta_id})",
            recipients=[destinatario],
            html=body_html
        )

        mail.send(msg)
        return True

    except Exception as e:
        print("ERROR AL ENVIAR CORREO:", e)
        return False

def eliminar_venta_y_restaurar_stock(venta_id):
    """
    Función que elimina la venta de la tabla ventas y sus detalles, 
    y restaura el stock. Útil para la eliminación permanente.
    """
    conn = db_connector()
    if conn is None:
        return False, "Error de conexión a la base de datos."
    
    cursor = conn.cursor()

    try:
        # 1. Obtener detalles de la venta (productos y cantidades)
        cursor.execute("SELECT producto_id, cantidad FROM detalles_venta WHERE venta_id = %s", [venta_id])
        detalles_venta = cursor.fetchall()

        if not detalles_venta:
            # Si no hay detalles, simplemente eliminamos la venta
            cursor.execute("DELETE FROM ventas WHERE id = %s", [venta_id])
            conn.commit()
            conn.close()
            return True, f"Venta #{venta_id} eliminada (no tenía detalles de producto)."

        # 2. Restaurar el stock de cada producto
        for producto_id, cantidad in detalles_venta:
            cursor.execute("UPDATE productos SET stock = stock + %s WHERE id = %s", (cantidad, producto_id))
        
        # 3. Eliminar los detalles de la venta
        cursor.execute("DELETE FROM detalles_venta WHERE venta_id = %s", [venta_id])
        
        # 4. Eliminar la venta
        cursor.execute("DELETE FROM ventas WHERE id = %s", [venta_id])
        
        conn.commit()
        conn.close()
        return True, f"Venta #{venta_id} eliminada permanentemente y stock restaurado."

    except Exception as e:
        conn.rollback()
        conn.close()
        print(f"Error de SQL al eliminar venta: {e}")
        return False, f"Error al eliminar la venta en la base de datos: {e}"

def procesar_devolucion(venta_id):
    """
    Función que revierte la venta, restaura el stock y marca la venta como 'Devuelta' (estado=0).
    """
    conn = db_connector()
    if conn is None:
        return False, "Error de conexión a la base de datos."
    
    cursor = conn.cursor()
    
    try:
        # 1. Obtener detalles de la venta
        cursor.execute("SELECT producto_id, cantidad FROM detalles_venta WHERE venta_id = %s", [venta_id])
        detalles_venta = cursor.fetchall()

        # 2. Restaurar el stock de cada producto
        for producto_id, cantidad in detalles_venta:
            cursor.execute("UPDATE productos SET stock = stock + %s WHERE id = %s", (cantidad, producto_id))
        
        # 3. Marcar la venta como cancelada/devuelta (estado = 0) y total = 0
        cursor.execute("UPDATE ventas SET estado = 0, total = 0.00 WHERE id = %s", [venta_id])
        
        conn.commit()
        conn.close()
        return True, f"Devolución de Venta #{venta_id} procesada exitosamente y stock restaurado."

    except Exception as e:
        conn.rollback()
        conn.close()
        print(f"Error de SQL al procesar devolución: {e}")
        return False, f"Error al procesar la devolución en la base de datos: {e}"


# -------------------------------------------------------------------
# RUTAS DE AUTENTICACIÓN Y SESIÓN
# -------------------------------------------------------------------

@app.route('/')
def index():
    """Redirige al login si no hay sesión iniciada."""
    if 'loggedin' in session:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        conn = db_connector()
        if conn is None:
            flash("Error de conexión a la base de datos.", 'error')
            return render_template('login.html')

        email = request.form.get('email')
        password_ingresada = request.form.get('password')

        cursor = conn.cursor(dictionary=True)

        try:
            query = "SELECT id, nombre, email, password_hash, rol FROM usuarios WHERE email = %s"
            cursor.execute(query, (email,))
            usuario = cursor.fetchone()

            if usuario:
                if bcrypt.check_password_hash(usuario['password_hash'], password_ingresada):
                    session['loggedin'] = True
                    session['id'] = usuario['id']
                    session['nombre'] = usuario['nombre']
                    session['rol'] = usuario['rol']

                    flash(f"¡Bienvenido, {usuario['nombre'].split()[0]}!", 'success')
                    return redirect(url_for('dashboard'))
                else:
                    flash('Contraseña incorrecta.', 'error')
            else:
                flash('Correo electrónico o usuario no encontrado.', 'error')

        except mysql.connector.Error as err:
            flash(f"Error al ejecutar consulta: {err}", 'error')

        finally:
            cursor.close()
            conn.close()

    return render_template('login.html')
    
@app.route('/registro', methods=['GET', 'POST'])
def registro():
    if request.method == 'POST':
        conn = db_connector() 
        if conn is None:
            flash("Error de conexión a la base de datos.", 'error')
            return render_template('registro.html')
            
        nombre = request.form['nombre']
        email = request.form['email'] 
        password_raw = request.form['password']
        rol = request.form.get('rol', 'vendedor')

        password_hash = bcrypt.generate_password_hash(password_raw).decode('utf-8')
        
        cursor = conn.cursor()

        try:
            # 2. Verificar duplicidad
            cursor.execute('SELECT id FROM usuarios WHERE email = %s', (email,))
            if cursor.fetchone():
                flash('El email ya está registrado.', 'warning')
                conn.close()
                return redirect(url_for('registro'))
            
            # 3. Inserción 
            cursor.execute(
                'INSERT INTO usuarios (nombre, email, password_hash, rol) VALUES (%s, %s, %s, %s)',
                (nombre, email, password_hash, rol)
            )

            conn.commit()
            flash("Usuario registrado correctamente", "success")
            return redirect(url_for('login'))

        except Exception as e:
            conn.rollback()
            flash(f"Error al registrar usuario: {e}", "danger")
            print(f"Error al registrar usuario: {e}")
        finally:
            cursor.close()
            conn.close()

    return render_template('registro.html')

@app.route('/logout')
def logout():
    """Cierra la sesión del usuario."""
    session.clear() 
    flash('Has cerrado sesión correctamente.', 'info')
    return redirect(url_for('login'))

# -------------------------------------------------------------------
# RUTAS DE RECUPERACIÓN DE CONTRASEÑA 
# -------------------------------------------------------------------

@app.route('/olvidar_contrasena', methods=['GET', 'POST'])
def olvidar_contrasena():
    """Muestra el formulario para solicitar la recuperación de contraseña y envía el código."""
    if request.method == 'POST':
        email = request.form.get('email')
        conn = db_connector()

        if conn is None:
            flash("Error de conexión a la base de datos.", 'danger')
            return render_template('olvidar_contrasena.html')

        cursor = conn.cursor()

        try:
            # 1. Buscar usuario
            cursor.execute("SELECT id, nombre FROM usuarios WHERE email = %s", (email,))
            user = cursor.fetchone()

            if user:
                user_id = user[0]
                user_nombre = user[1].split()[0] # Solo el primer nombre
                
                # 2. Generar código y fecha de expiración (15 minutos)
                reset_code = secrets.token_hex(3).upper() # Código de 6 caracteres
                expiration_time = datetime.now() + timedelta(minutes=15) # Tiempo de expiración

                # Actualiza el token y la fecha de expiración. 
                # (Asumiendo que `reset_token_expiracion` fue agregado a la tabla `usuarios`)
                cursor.execute(
                    "UPDATE usuarios SET reset_token = %s, reset_token_expiracion = %s WHERE id = %s", 
                    (reset_code, expiration_time, user_id)
                )
                conn.commit()
                
                # 3. Enviar correo de recuperación
                msg = Message(
                    subject="Recuperación de Contraseña",
                    recipients=[email],
                    html=f"""
                    <html>
                    <body style="font-family: Arial;">
                        <div style="max-width:600px;margin:auto;padding:20px;border:1px solid #ddd;border-radius:10px;">
                            <h2 style="color:#4285F4;">Hola {user_nombre}, Solicitud de Recuperación</h2>
                            <p>Hemos recibido una solicitud para restablecer tu contraseña.</p>
                            <p>Tu código de recuperación es:</p>
                            <div style="background-color:#f4f4f4;padding:15px;text-align:center;font-size:24px;font-weight:bold;margin:20px 0;">
                                {reset_code}
                            </div>
                            <p>Este código expira en 15 minutos. Puedes usar el código en el siguiente enlace:</p>
                            <a href="{url_for('recuperar_contrasena_form', _external=True)}" 
                                style="display:inline-block;padding:10px 20px;background-color:#34A853;color:white;text-decoration:none;border-radius:5px;">
                                Ir a Formulario de Recuperación
                            </a>
                        </div>
                    </body>
                    </html>
                    """
                )
                mail.send(msg)
                
                flash('Se ha enviado un código de recuperación a tu correo electrónico. Revisa tu bandeja de entrada y spam.', 'success')
                return redirect(url_for('recuperar_contrasena_form'))
            else:
                flash('El correo electrónico no está registrado.', 'warning')

        except Exception as e:
            flash(f'Ocurrió un error al procesar la solicitud: {e}', 'danger')
            print(f"Error en olvidar_contrasena: {e}")
        finally:
            if conn and conn.is_connected():
                conn.close()

    return render_template('olvidar_contrasena.html')

@app.route('/recuperar_contrasena', methods=['GET'])
def recuperar_contrasena_form():
    """Muestra el formulario para ingresar el código y la nueva contraseña."""
    return render_template('recuperar_contrasena.html')

@app.route('/recuperar_contrasena', methods=['POST'])
def recuperar_contrasena_post():
    """Procesa el código de recuperación y actualiza la contraseña."""
    reset_code = request.form.get('reset_code')
    new_password = request.form.get('new_password')
    
    if not reset_code or not new_password:
        flash("Debes ingresar el código de recuperación y la nueva contraseña.", 'danger')
        return redirect(url_for('recuperar_contrasena_form'))

    conn = db_connector()
    if conn is None:
        flash("Error de conexión a la base de datos.", 'danger')
        return redirect(url_for('login'))
        
    cursor = conn.cursor()

    try:
        # 1. Buscar usuario por token Y verificar que no haya expirado (reset_token_expiracion > NOW())
        cursor.execute("""
            SELECT id FROM usuarios 
            WHERE reset_token = %s 
            AND reset_token IS NOT NULL
            AND reset_token_expiracion > NOW()
        """, (reset_code,))
        user = cursor.fetchone()

        if user:
            user_id = user[0]
            
            # 2. Generar hash de la nueva contraseña
            password_hash = bcrypt.generate_password_hash(new_password).decode('utf-8')
            
            # 3. Actualizar contraseña y eliminar el token y su expiración
            cursor.execute(
                "UPDATE usuarios SET password_hash = %s, reset_token = NULL, reset_token_expiracion = NULL WHERE id = %s",
                (password_hash, user_id)
            )
            conn.commit()
            
            flash('Tu contraseña ha sido restablecida exitosamente. ¡Ya puedes iniciar sesión!', 'success')
            return redirect(url_for('login'))
        else:
            # El código puede ser inválido o haber expirado
            flash('Código de recuperación inválido o expirado.', 'danger')
            return redirect(url_for('recuperar_contrasena_form'))

    except Exception as e:
        conn.rollback()
        flash(f'Error al restablecer la contraseña: {e}', 'danger')
        print(f"Error en recuperar_contrasena_post: {e}")
        return redirect(url_for('recuperar_contrasena_form'))
    finally:
        if conn and conn.is_connected():
            conn.close()

# -------------------------------------------------------------------
# RUTAS PRINCIPALES Y CRUD
# -------------------------------------------------------------------

@app.route('/dashboard')
@login_required
def dashboard():
    """Muestra el panel de control principal con métricas y datos para gráficos."""
    conn = db_connector()
    if conn is None:
        flash("Error de conexión a la base de datos.", 'danger')
        return redirect(url_for('login')) 
    
    cursor = conn.cursor()
    
    # --- 1. CÁLCULO DE MÉTRICAS CLAVE (KPIs) ---
    
    cursor.execute("SELECT COUNT(id) FROM usuarios")
    usuarios_activos = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(id) FROM clientes WHERE fecha_registro >= DATE_SUB(CURDATE(), INTERVAL 30 DAY)")
    nuevos_clientes = cursor.fetchone()[0]
    
    cursor.execute("""
        SELECT IFNULL(SUM(total), 0.00) FROM ventas 
        WHERE MONTH(fecha) = MONTH(CURDATE()) AND YEAR(fecha) = YEAR(CURDATE()) AND estado = 1
    """)
    ingresos_mes = cursor.fetchone()[0] 
    
    tareas_pendientes = 0 # Deja 0 si no tienes una tabla 'tareas'
    
    
    # --- 2. DATOS PARA GRÁFICOS (Ventas de los últimos 7 días) ---
    
    cursor.execute("""
        SELECT DATE(fecha), IFNULL(SUM(total), 0.00)
        FROM ventas
        WHERE fecha >= DATE_SUB(CURDATE(), INTERVAL 7 DAY) AND estado = 1
        GROUP BY DATE(fecha)
        ORDER BY DATE(fecha) ASC
    """)
    ventas_por_dia = cursor.fetchall()

    conn.close()

    # --- 3. PREPARAR DATOS Y ENVIAR A LA PLANTILLA ---
    
    dias = [item[0].strftime('%Y-%m-%d') for item in ventas_por_dia]
    totales = [float(item[1]) for item in ventas_por_dia]

    metricas = {
        'Usuarios Activos': usuarios_activos,
        'Ingresos (Mes)': ingresos_mes,
        'Tareas Pendientes': tareas_pendientes,
        'Nuevos Clientes': nuevos_clientes
    }

    return render_template('dashboard.html', 
                           metricas=metricas,
                           dias=dias, 
                           totales=totales)
# --- RUTAS DE CLIENTES (CRUD) ---

@app.route('/clientes', methods=['GET'])
@login_required
def listar_clientes():
    """Muestra la lista de todos los clientes."""
    conn = db_connector()
    if conn is None:
        flash("Error de conexión a la base de datos.", 'danger')
        return redirect(url_for('dashboard'))

    # Se incluye 'direccion' en la consulta
    cursor = conn.cursor()
    cursor.execute("SELECT id, nombre, apellido, email, telefono, direccion FROM clientes ORDER BY fecha_registro DESC")
    clientes = cursor.fetchall()
    conn.close()

    # Nota: Asegúrate de actualizar clientes.html para mostrar la dirección si es necesario
    return render_template('clientes.html', clientes=clientes)

@app.route('/clientes/nuevo', methods=['GET', 'POST'])
@login_required
def crear_cliente():
    """Muestra el formulario (GET) y maneja el registro de un nuevo cliente (POST)."""
    conn = None
    
    # ----------------------------------------------------
    # Lógica de Manejo POST (Cuando se envía el formulario)
    # ----------------------------------------------------
    if request.method == 'POST':
        nombre = request.form['nombre']
        apellido = request.form.get('apellido')
        email = request.form['email']
        telefono = request.form.get('telefono')
        direccion = request.form.get('direccion') # Ahora manejando el nuevo campo

        if not nombre or not email:
            flash('El nombre y el correo son obligatorios.', 'danger')
            return render_template('crear_cliente.html', 
                                   nombre=nombre, apellido=apellido, email=email, 
                                   telefono=telefono, direccion=direccion) # Vuelve a renderizar el formulario con los datos enviados

        conn = db_connector()
        if conn is None:
            flash("Error de conexión a la base de datos.", 'danger')
            return redirect(url_for('crear_cliente'))
            
        try:
            cursor = conn.cursor()
            cursor.execute(
                # La consulta INSERT ahora incluye 'direccion'
                "INSERT INTO clientes (nombre, apellido, email, telefono, direccion) VALUES (%s, %s, %s, %s, %s)",
                (nombre, apellido, email, telefono, direccion)
            )
            conn.commit()
            flash(f'Cliente {nombre} {apellido if apellido else ""} registrado exitosamente.', 'success')
            return redirect(url_for('listar_clientes')) 
        
        except mysql.connector.errors.IntegrityError as e:
            conn.rollback()
            if e.errno == 1062:
                flash(f'El correo electrónico "{email}" ya está registrado. Por favor, ingrese uno diferente.', 'warning')
            else:
                flash(f'Error de integridad de datos al registrar cliente: {e}', 'danger')
            # Vuelve a la página del formulario en caso de error
            return render_template('crear_cliente.html', 
                                   nombre=nombre, apellido=apellido, email=email, 
                                   telefono=telefono, direccion=direccion) 

        except Exception as e:
            conn.rollback()
            flash(f'Error al registrar cliente: {e}', 'danger')
            print(f'Error al registrar cliente: {e}')
            return redirect(url_for('crear_cliente')) 
        finally:
            if conn and conn.is_connected():
                conn.close()

    # ----------------------------------------------------
    # Lógica de Manejo GET (Cuando se hace clic en el botón)
    # ----------------------------------------------------
    # Se añade manejo de datos vacíos para que la plantilla no falle al intentar acceder a variables inexistentes
    return render_template('crear_cliente.html', nombre='', apellido='', email='', telefono='', direccion='')


@app.route('/clientes/editar/<int:cliente_id>', methods=['GET', 'POST'])
@login_required
def editar_cliente(cliente_id):
    """Muestra el formulario de edición y procesa la actualización del cliente."""
    # ... (Tu código para editar_cliente, que ya parece manejar 'direccion')
    # ... (No necesita cambios a menos que la base de datos tenga un índice UNIQUE en email/teléfono)
    conn = db_connector()
    if conn is None:
        flash("Error de conexión a la base de datos.", 'danger')
        return redirect(url_for('listar_clientes'))
        
    cursor = conn.cursor(dictionary=True) 
    
    if request.method == 'POST':
        nombre = request.form['nombre']
        apellido = request.form.get('apellido')
        email = request.form['email']
        telefono = request.form.get('telefono')
        direccion = request.form.get('direccion')

        try:
            cursor.execute(
                "UPDATE clientes SET nombre=%s, apellido=%s, email=%s, telefono=%s, direccion=%s WHERE id=%s",
                (nombre, apellido, email, telefono, direccion, cliente_id)
            )
            conn.commit()
            flash(f'Cliente ID {cliente_id} actualizado exitosamente.', 'success')
            return redirect(url_for('listar_clientes'))
        except mysql.connector.errors.IntegrityError as e:
            conn.rollback()
            # Este manejo es útil si el email debe ser único (Error 1062)
            if e.errno == 1062:
                flash(f'El correo electrónico "{email}" ya está registrado en otro cliente. Por favor, ingrese uno diferente.', 'warning')
            else:
                flash(f'Error de integridad de datos al actualizar cliente: {e}', 'danger')
            # Re-fetch the client data if there was an error, to keep the edit page open
            cursor.execute("SELECT id, nombre, apellido, email, telefono, direccion FROM clientes WHERE id = %s", [cliente_id])
            cliente = cursor.fetchone()
            if cliente:
                return render_template('editar_cliente.html', cliente=cliente)
            return redirect(url_for('listar_clientes'))
        except Exception as e:
            conn.rollback()
            flash(f'Error al actualizar el cliente: {e}', 'danger')
        finally:
            conn.close()

    # GET request
    cursor.execute("SELECT id, nombre, apellido, email, telefono, direccion FROM clientes WHERE id = %s", [cliente_id])
    cliente = cursor.fetchone()
    conn.close()

    if cliente:
        return render_template('editar_cliente.html', cliente=cliente)
    else:
        flash('Cliente no encontrado.', 'danger')
        return redirect(url_for('listar_clientes'))


@app.route('/clientes/eliminar/<int:cliente_id>', methods=['POST'])
@login_required
def eliminar_cliente(cliente_id):
    """Maneja la eliminación de un cliente."""
    # ... (Tu código para eliminar_cliente)
    if request.method == 'POST':
        conn = db_connector()
        if conn is None:
            flash("Error de conexión a la base de datos.", 'danger')
            return redirect(url_for('listar_clientes'))
            
        try:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM clientes WHERE id = %s", [cliente_id])
            conn.commit()
            flash(f'Cliente ID {cliente_id} eliminado correctamente.', 'success')
        except mysql.connector.errors.IntegrityError:
            conn.rollback()
            flash('No se puede eliminar el cliente porque tiene ventas asociadas.', 'danger')
        except Exception as e:
            conn.rollback()
            flash(f'Error al eliminar el cliente: {e}', 'danger')
        finally:
            conn.close()

    return redirect(url_for('listar_clientes'))

# NOTA: ELIMINAR la función 'registrar_cliente' que estaba aquí.
    
# --- RUTAS DE PRODUCTOS (CRUD) ---

@app.route('/productos')
@login_required
def listar_productos():
    conn = None
    cursor = None
    productos = []
    try:
        conn = db_connector()
        cursor = conn.cursor()
        
        # Se elimina 'url_imagen' de la consulta SELECT
        cursor.execute("SELECT id, nombre, descripcion, precio, costo, stock, codigo_barra FROM productos ORDER BY id DESC")
        productos = cursor.fetchall()

    except Exception as e:
        flash(f'Error al cargar productos: {e}', 'danger')
        print(f"Error al listar productos: {e}")
    finally:
        if cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()

    return render_template('listar_productos.html', productos=productos)

@app.route('/productos/registrar', methods=['GET', 'POST'])
@login_required
def registrar_producto():
    conn = None
    cursor = None
    if request.method == 'POST':
        try:
            conn = db_connector()
            cursor = conn.cursor()

            # Se eliminó la variable 'url_imagen'
            nombre = request.form['nombre']
            descripcion = request.form['descripcion']
            precio = float(request.form['precio'])
            costo = float(request.form['costo'])
            stock = int(request.form['stock'])
            codigo_barra = request.form['codigo_barra']
            
            # Consulta INSERT corregida (sin url_imagen)
            cursor.execute("""
                INSERT INTO productos (nombre, descripcion, precio, costo, stock, codigo_barra)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (nombre, descripcion, precio, costo, stock, codigo_barra))
            
            conn.commit()
            flash('¡Producto registrado con éxito!', 'success')
            return redirect(url_for('listar_productos'))
        
        except Exception as e:
            if conn:
                conn.rollback()
            flash(f'Error al registrar el producto: {e}', 'danger')
            print(f"Error al registrar producto: {e}")
            return redirect(url_for('registrar_producto'))
        finally:
            if cursor:
                cursor.close()
            if conn and conn.is_connected():
                conn.close()
    
    return render_template('registrar_producto.html')  

@app.route('/productos/eliminar/<int:producto_id>', methods=['POST'])
@login_required
def eliminar_producto(producto_id):
    """Maneja la eliminación de un producto."""
    if request.method == 'POST':
        conn = db_connector()
        if conn is None:
            flash("Error de conexión a la base de datos.", 'danger')
            return redirect(url_for('listar_productos'))
            
        try:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM productos WHERE id = %s", [producto_id])
            conn.commit()
            flash(f'Producto ID {producto_id} eliminado correctamente.', 'success')
        except Exception as e:
            conn.rollback()
            flash(f'Error al eliminar el producto (puede tener ventas asociadas): {e}', 'danger')
        finally:
            conn.close()

    return redirect(url_for('listar_productos'))
    
@app.route('/productos/editar/<int:id>', methods=['GET', 'POST'])
@login_required
def editar_producto(id):
    conn = None
    cursor = None
    try:
        conn = db_connector()
        cursor = conn.cursor()

        if request.method == 'POST':
            # Obtener datos del formulario
            nombre = request.form['nombre']
            descripcion = request.form['descripcion']
            precio = float(request.form['precio'])
            costo = float(request.form['costo'])
            stock = int(request.form['stock'])
            codigo_barra = request.form['codigo_barra']

            # Actualizar producto
            cursor.execute("""
                UPDATE productos
                SET nombre=%s, descripcion=%s, precio=%s, costo=%s, stock=%s, codigo_barra=%s
                WHERE id=%s
            """, (nombre, descripcion, precio, costo, stock, codigo_barra, id))
            conn.commit()

            flash('¡Producto actualizado con éxito!', 'success')
            return redirect(url_for('listar_productos'))

        # GET: Cargar datos actuales del producto
        cursor.execute("""
            SELECT nombre, descripcion, precio, costo, stock, codigo_barra
            FROM productos
            WHERE id=%s
        """, (id,))
        producto = cursor.fetchone()

        if not producto:
            flash('Producto no encontrado', 'danger')
            return redirect(url_for('listar_productos'))

        # Pasar datos a la plantilla
        return render_template('editar_producto.html', producto=producto, id=id)

    except Exception as e:
        if conn:
            conn.rollback()
        flash(f'Error al cargar o actualizar el producto: {e}', 'danger')
        print(f"Error editar_producto: {e}")
        return redirect(url_for('listar_productos'))

    finally:
        if cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()


# --- RUTAS DE VENTAS ---

# =================================================================
# GESTIÓN DE DEVOLUCIONES
# =================================================================
@app.route('/ventas/devolucion/<int:venta_id>', methods=['GET', 'POST'])
@login_required
def nueva_devolucion(venta_id):

    conn = None
    cursor = None

    try:
        conn = db_connector()
        if conn is None:
            flash("Error de conexión a la base de datos.", 'danger')
            return redirect(url_for('listar_ventas'))

        cursor = conn.cursor(dictionary=True)

        # =============================================================
        # 1. SI ES GET → MOSTRAR FORMULARIO
        # =============================================================
        if request.method == 'GET':

            cursor.execute("""
                SELECT v.id, v.fecha, v.total,
                       CONCAT(c.nombre, ' ', c.apellido) AS cliente_nombre,
                       v.estado
                FROM ventas v
                JOIN clientes c ON v.cliente_id = c.id
                WHERE v.id = %s
            """, (venta_id,))
            venta_info = cursor.fetchone()

            if not venta_info:
                flash(f"Venta con ID {venta_id} no encontrada.", 'danger')
                return redirect(url_for('listar_ventas'))

            # Venta cancelada → No permitir devolución
            if venta_info["estado"] != 1:
                flash(f"La Venta #{venta_id} no puede ser devuelta porque está Cancelada.", 'warning')
                return redirect(url_for('detalle_venta', venta_id=venta_id))

            cursor.execute("""
                SELECT dv.producto_id, p.nombre, dv.cantidad,
                       dv.precio_unitario, dv.subtotal
                FROM detalles_venta dv
                JOIN productos p ON dv.producto_id = p.id
                WHERE dv.venta_id = %s
            """, (venta_id,))
            detalles = cursor.fetchall()

            return render_template(
                'registrar_devolucion.html',
                venta=[
                    venta_info["id"],
                    venta_info["fecha"],
                    venta_info["total"],
                    venta_info["cliente_nombre"],
                    venta_info["estado"]
                ],
                detalles=[(
                    d["producto_id"],
                    d["nombre"],
                    d["cantidad"],
                    d["precio_unitario"],
                    d["subtotal"]
                ) for d in detalles]
            )

        # =============================================================
        # 2. SI ES POST → PROCESAR DEVOLUCIÓN
        # =============================================================
        producto_ids = request.form.getlist("producto_id[]")

        if not producto_ids:
            flash("No seleccionaste ningún producto para devolver.", 'warning')
            return redirect(url_for('detalle_venta', venta_id=venta_id))

        total_devolucion = 0
        items_devolver = []   # Para registrar detalles

        for producto_id in producto_ids:
            devolver_cant = int(request.form.get(f"devolver_cantidad_{producto_id}", 0))
            cant_original = int(request.form.get(f"cantidad_original_{producto_id}", 0))
            precio_unit = float(request.form.get(f"precio_unitario_{producto_id}", 0))

            if devolver_cant > 0:
                if devolver_cant > cant_original:
                    flash("Cantidad a devolver inválida.", 'danger')
                    return redirect(url_for('nueva_devolucion', venta_id=venta_id))

                subtotal = devolver_cant * precio_unit
                total_devolucion += subtotal
                items_devolver.append((producto_id, devolver_cant, precio_unit, subtotal))

        if len(items_devolver) == 0:
            flash("No ingresaste cantidades válidas para devolver.", 'warning')
            return redirect(url_for('nueva_devolucion', venta_id=venta_id))

        # =============================================================
        # GUARDAR DEVOLUCIÓN EN BD
        # =============================================================
        cursor.execute("""
            INSERT INTO devoluciones (venta_id, total, fecha)
            VALUES (%s, %s, NOW())
        """, (venta_id, total_devolucion))
        devolucion_id = cursor.lastrowid

        # Registrar detalle
        for producto_id, cant_dev, precio, subtotal in items_devolver:

            cursor.execute("""
                INSERT INTO detalles_devolucion
                (devolucion_id, producto_id, cantidad, precio, subtotal)
                VALUES (%s, %s, %s, %s, %s)
            """, (devolucion_id, producto_id, cant_dev, precio, subtotal))

            # Devolver al inventario
            cursor.execute("""
                UPDATE productos SET stock = stock + %s WHERE id = %s
            """, (cant_dev, producto_id))

        # Marcar venta como devuelta (estado = 0)
        cursor.execute("""
            UPDATE ventas SET estado = 0 WHERE id = %s
        """, (venta_id,))

        conn.commit()

        flash("¡Devolución procesada correctamente!", "success")
        return redirect(url_for('detalle_venta', venta_id=venta_id))

    except Exception as e:
        print("Error en nueva_devolucion:", e)
        if conn:
            conn.rollback()
        flash(f"Error al procesar la devolución: {e}", 'danger')
        return redirect(url_for('detalle_venta', venta_id=venta_id))

    finally:
        if cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()



@app.route('/ventas/devolver/<int:venta_id>', methods=['POST'])
@login_required
def procesar_devolucion(venta_id):
    """
    Procesa la devolución de una venta:
    - Verifica que la venta exista y esté activa
    - Restaura el stock de los productos
    - Marca la venta como anulada (estado = 0)
    """
    conn = None
    try:
        conn = db_connector()
        cursor = conn.cursor(dictionary=True)

        # 1️⃣ Verificar que la venta exista y esté activa
        cursor.execute("""
            SELECT id, estado
            FROM ventas
            WHERE id = %s
        """, (venta_id,))
        venta = cursor.fetchone()

        if not venta:
            flash('La venta no existe.', 'danger')
            return redirect(url_for('listar_ventas'))

        if venta['estado'] == 0:
            flash('Esta venta ya fue anulada.', 'warning')
            return redirect(url_for('listar_ventas'))

        # 2️⃣ Obtener productos vendidos para restaurar stock
        cursor.execute("""
            SELECT producto_id, cantidad
            FROM detalles_venta
            WHERE venta_id = %s
        """, (venta_id,))
        detalles = cursor.fetchall()

        # 3️⃣ Restaurar stock de cada producto
        for item in detalles:
            cursor.execute("""
                UPDATE productos
                SET stock = stock + %s
                WHERE id = %s
            """, (item['cantidad'], item['producto_id']))

        # 4️⃣ Marcar la venta como anulada
        cursor.execute("""
            UPDATE ventas
            SET estado = 0
            WHERE id = %s
        """, (venta_id,))

        conn.commit()

        flash('Devolución procesada correctamente. Stock restaurado.', 'success')
        return redirect(url_for('listar_ventas'))

    except Exception as e:
        if conn:
            conn.rollback()
        flash(f'Error al procesar la devolución: {e}', 'danger')
        print(f'Error al procesar la devolución: {e}')
        return redirect(url_for('listar_ventas'))

    finally:
        if conn and conn.is_connected():
            conn.close()



@app.route('/ventas/registrar', methods=['GET', 'POST'])
@login_required
def registrar_venta():

    conn = None
    cursor = None
    today = date.today().strftime('%Y-%m-%d')

    try:
        conn = db_connector()
        if conn is None:
            flash("Error de conexión a la base de datos.", "danger")
            return redirect(url_for('dashboard'))
        
        cursor = conn.cursor()

        # =====================================================
        # ===============   PROCESAR POST   ====================
        # =====================================================
        if request.method == 'POST':

            cliente_id_str = request.form.get('cliente_id')
            fecha_str = request.form.get('fecha')
            total_venta_str = request.form.get('total_final')
            descuento_porc_str = request.form.get('descuento_porc', '0')
            metodo_pago = request.form.get('metodo_pago')

            if not cliente_id_str or not cliente_id_str.isdigit():
                raise ValueError("Cliente inválido.")

            if not total_venta_str:
                raise ValueError("El total de la venta no puede ser vacío.")

            cliente_id = int(cliente_id_str)
            descuento_porc = float(descuento_porc_str)
            total_venta = float(total_venta_str)

            try:
                fecha = datetime.strptime(fecha_str, "%Y-%m-%d").date()
            except:
                fecha = date.today()

            usuario_id = session.get('id')

            # ================================================
            # 1. INSERTAR ENCABEZADO DE VENTA
            # ================================================
            cursor.execute("""
                INSERT INTO ventas (cliente_id, fecha, total, usuario_id, metodo_pago, descuento_porc, estado)
                VALUES (%s, %s, %s, %s, %s, %s, 1)
            """, (cliente_id, fecha, total_venta, usuario_id, metodo_pago, descuento_porc))

            venta_id = cursor.lastrowid

            # ================================================
            # 2. PROCESAR DETALLES DE VENTA
            # ================================================
            productos_ids = request.form.getlist('producto_id[]')
            cantidades = request.form.getlist('cantidad[]')
            precios_unitarios = request.form.getlist('producto_precio_unitario[]')
            subtotales_item = request.form.getlist('subtotal_item[]')

            if not productos_ids:
                raise ValueError("No se enviaron productos.")

            detalles_correo = []   # ← Para la factura

            for i in range(len(productos_ids)):

                pid = productos_ids[i]
                cant = cantidades[i]
                precio = precios_unitarios[i]
                subtotal = subtotales_item[i]

                # ---- FILTRAR FILAS INVÁLIDAS ----
                if not pid or not pid.isdigit():
                    continue
                if not cant or not cant.isdigit():
                    continue
                try:
                    precio_f = float(precio)
                    subtotal_f = float(subtotal)
                except:
                    continue
                if subtotal_f <= 0:
                    continue

                cantidad_i = int(cant)
                producto_id_i = int(pid)

                # ---- INSERTAR DETALLE ----
                cursor.execute("""
                    INSERT INTO detalles_venta (venta_id, producto_id, cantidad, precio_unitario, subtotal)
                    VALUES (%s, %s, %s, %s, %s)
                """, (venta_id, producto_id_i, cantidad_i, precio_f, subtotal_f))

                # ---- ACTUALIZAR STOCK ----
                cursor.execute("""
                    UPDATE productos SET stock = stock - %s WHERE id = %s
                """, (cantidad_i, producto_id_i))

                # ---- OBTENER NOMBRE PARA LA FACTURA ----
                cursor.execute("SELECT nombre FROM productos WHERE id=%s", (producto_id_i,))
                nombre_producto = cursor.fetchone()[0]

                detalles_correo.append((nombre_producto, cantidad_i, precio_f, subtotal_f))

            # Validación final
            if len(detalles_correo) == 0:
                raise ValueError("No hay productos válidos para generar la factura.")

            # ================================================
            # 3. DATOS PARA LA FACTURA Y CORREO
            # ================================================
            cursor.execute("SELECT nombre, apellido, email FROM clientes WHERE id=%s", (cliente_id,))
            cliente_data = cursor.fetchone()

            if cliente_data:
                nombre_cliente = f"{cliente_data[0]} {cliente_data[1]}"
                correo_cliente = cliente_data[2]
            else:
                nombre_cliente = "Cliente"
                correo_cliente = None

            # ¿Es primera compra?
            cursor.execute("SELECT COUNT(*) FROM ventas WHERE cliente_id=%s AND estado = 1", (cliente_id,))
            num_compras = cursor.fetchone()[0]
            es_primera = True if num_compras == 1 else False

            # ================================================
            # 4. ENVIAR CORREO (si tiene correo)
            # ================================================
            if correo_cliente:
                # La función auxiliar manejará el envío y la verificación de errores
                enviar_factura_por_correo(
                    destinatario=correo_cliente,
                    venta_id=venta_id,
                    total=total_venta,
                    detalles_productos=detalles_correo,
                    descuento_aplicado=descuento_porc,
                    es_primera_compra=es_primera,
                    nombre_cliente=nombre_cliente
                )

            conn.commit()
            flash(f"¡Venta #{venta_id} registrada correctamente!", "success")
            return redirect(url_for('listar_ventas'))

        # ======================================================
        # ===============  GET → MOSTRAR FORMULARIO  ===========
        # ======================================================
        cursor.execute("SELECT id, CONCAT(nombre, ' ', apellido, ' (', email, ')') FROM clientes")
        clientes = cursor.fetchall()

        cursor.execute("SELECT id, nombre, precio, stock FROM productos WHERE stock > 0 ORDER BY nombre")
        productos = cursor.fetchall()

        return render_template('registrar_venta.html', clientes=clientes, productos=productos, today=today)

    except Exception as e:
        if conn: conn.rollback()
        flash(f"Error al registrar venta: {e}", "danger")
        print("ERROR registrar_venta:", e)
        return redirect(url_for('registrar_venta'))

    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()

            
@app.route('/ventas')
@login_required
def listar_ventas():
    conn = db_connector()
    if conn is None:
        flash("Error de conexión a la base de datos.", "danger")
        return redirect(url_for('dashboard'))

    cursor = conn.cursor()

    cursor.execute("""
        SELECT 
            v.id,
            v.fecha,
            CONCAT(c.nombre, ' ', c.apellido) AS cliente,
            v.total,
            v.metodo_pago,
            v.estado
        FROM ventas v
        LEFT JOIN clientes c ON v.cliente_id = c.id
        ORDER BY v.fecha DESC
    """)

    ventas = cursor.fetchall()
    conn.close()

    return render_template('listar_ventas.html', ventas=ventas)

    
@app.route('/ventas/detalle/<int:venta_id>', methods=['GET'])
@login_required
def detalle_venta(venta_id):
    """Muestra el detalle de una venta específica."""
    conn = db_connector()
    if conn is None:
        flash("Error de conexión a la base de datos.", 'danger')
        return redirect(url_for('listar_ventas'))
        
    cursor = conn.cursor(dictionary=True) # Usar diccionario para facilitar acceso

    # 1. Obtener información de la venta principal
    cursor.execute("""
        SELECT v.id, v.fecha, v.total, v.estado, v.metodo_pago, v.descuento_porc, 
               c.nombre as cliente_nombre, c.apellido as cliente_apellido, c.email as cliente_email,
               u.nombre as vendedor_nombre
        FROM ventas v
        JOIN clientes c ON v.cliente_id = c.id
        JOIN usuarios u ON v.usuario_id = u.id
        WHERE v.id = %s
    """, [venta_id])
    venta_info = cursor.fetchone()

    if not venta_info:
        conn.close()
        flash('Venta no encontrada.', 'danger')
        return redirect(url_for('listar_ventas'))

    # 2. Obtener detalles de productos
    cursor.execute("""
        SELECT dv.cantidad, dv.precio_unitario, dv.subtotal, p.nombre as producto_nombre
        FROM detalles_venta dv
        JOIN productos p ON dv.producto_id = p.id
        WHERE dv.venta_id = %s
    """, [venta_id])
    detalles = cursor.fetchall()
    
    conn.close()

    # El email del cliente está en venta_info['cliente_email']
    cliente_email = venta_info['cliente_email'] 
    
    return render_template('detalle_venta.html', venta=venta_info, detalles=detalles, cliente_email=cliente_email)


@app.route('/ventas/devolver/<int:venta_id>', methods=['POST'])
@login_required
def devolver_venta(venta_id):
    conn = None
    try:
        conn = db_connector()
        cursor = conn.cursor(dictionary=True)

        # 1️⃣ Verificar venta
        cursor.execute("""
            SELECT id, total, estado
            FROM ventas
            WHERE id = %s
        """, (venta_id,))
        venta = cursor.fetchone()

        if not venta:
            flash('La venta no existe.', 'danger')
            return redirect(url_for('listar_ventas'))

        if venta['estado'] == 0:
            flash('Esta venta ya fue devuelta o anulada.', 'warning')
            return redirect(url_for('listar_ventas'))

        # 2️⃣ Restaurar stock
        cursor.execute("""
            SELECT producto_id, cantidad
            FROM detalles_venta
            WHERE venta_id = %s
        """, (venta_id,))
        detalles = cursor.fetchall()

        for item in detalles:
            cursor.execute("""
                UPDATE productos
                SET stock = stock + %s
                WHERE id = %s
            """, (item['cantidad'], item['producto_id']))

        # 3️⃣ Marcar venta como devuelta (estado = 0)
        cursor.execute("""
            UPDATE ventas
            SET estado = 0
            WHERE id = %s
        """, (venta_id,))

        conn.commit()
        flash('Venta devuelta correctamente y stock restaurado.', 'success')
        return redirect(url_for('listar_ventas'))

    except Exception as e:
        if conn:
            conn.rollback()
        flash(f'Error al procesar la devolución: {e}', 'danger')
        print(f'ERROR DEVOLUCIÓN: {e}')
        return redirect(url_for('listar_ventas'))

    finally:
        if conn and conn.is_connected():
            conn.close()


@app.route('/ventas/eliminar/<int:venta_id>', methods=['POST'])
@login_required
def eliminar_venta(venta_id):
    """Maneja la eliminación de una venta confirmada."""
    exito, mensaje = eliminar_venta_y_restaurar_stock(venta_id)
    if exito:
        flash(mensaje, 'success')
    else:
        flash(mensaje, 'danger')
    return redirect(url_for('listar_ventas'))
    
@app.route('/ventas/enviar_factura/<int:venta_id>', methods=['POST'])
@login_required
def enviar_factura(venta_id):
    """ Obtiene el detalle de la venta y envía la factura por correo. """

    conn = db_connector()
    if conn is None:
        flash("Error de conexión a la base de datos.", 'danger')
        return redirect(url_for('detalle_venta', venta_id=venta_id))

    cursor = conn.cursor(dictionary=True)

    try:
        # 1. Datos principales de la venta + cliente
        cursor.execute("""
            SELECT v.*, 
                   c.email AS cliente_email, 
                   c.id AS cliente_id, 
                   c.nombre AS cliente_nombre, 
                   c.apellido AS cliente_apellido
            FROM ventas v
            JOIN clientes c ON v.cliente_id = c.id
            WHERE v.id = %s
        """, (venta_id,))
        venta_info = cursor.fetchone()

        if not venta_info:
            raise ValueError("Venta no encontrada.")

        cliente_email = venta_info.get('cliente_email')
        cliente_id = venta_info.get('cliente_id')

        total_venta = float(venta_info.get('total') or 0.0)

        descuento_aplicado = float(
            venta_info.get('descuento_porc') or
            venta_info.get('descuento') or
            venta_info.get('descuento_total') or
            0.0
        )

        # 2. Obtener detalles de la venta
        cursor.execute("""
            SELECT dv.cantidad, dv.precio_unitario, dv.subtotal, 
                   p.nombre AS producto_nombre 
            FROM detalles_venta dv
            JOIN productos p ON dv.producto_id = p.id
            WHERE dv.venta_id = %s
        """, (venta_id,))
        detalles = cursor.fetchall()

        detalles_tuplas = [
            (d['producto_nombre'], d['cantidad'], d['precio_unitario'], d['subtotal'])
            for d in detalles
        ]

        # 3. Determinar si es la primera compra (ARREGLADO)
        cursor.execute("""
            SELECT COUNT(id) AS num 
            FROM ventas 
            WHERE cliente_id = %s
        """, (cliente_id,))
        count_result = cursor.fetchone()

        num_compras = int(count_result.get('num', 0))
        es_primera_compra = (num_compras == 1)

        # 4. Nombre completo
        nombre = venta_info.get('cliente_nombre', '')
        apellido = venta_info.get('cliente_apellido', '')
        nombre_completo = f"{nombre} {apellido}".strip() or "Cliente"

        conn.close()

        # 5. Validar correo
        if not cliente_email or "@" not in cliente_email:
            flash(f"El cliente '{nombre_completo}' no tiene un correo válido. Factura no enviada.", 'danger')
            return redirect(url_for('detalle_venta', venta_id=venta_id))

        # 6. Enviar correo
        exito = enviar_factura_por_correo(
    destinatario=cliente_email,
    venta_id=venta_id,
    total=total_venta,
    detalles_productos=detalles_tuplas,
    descuento_aplicado=descuento_aplicado,
    es_primera_compra=verificar_si_es_primera_compra(cliente_id),
    nombre_cliente=nombre_completo
)

        if exito:
            flash(f"Factura de Venta #{venta_id} enviada a {cliente_email}.", 'success')
        else:
            flash("Error al enviar el correo. Revisa el SMTP o la clave de aplicación.", 'danger')

    except Exception as e:
        if conn and conn.is_connected():
            conn.close()

        print(f"Error en enviar_factura: {e}")
        flash(f"Error al preparar la factura (DB/Data error): {e}", 'danger')

    return redirect(url_for('detalle_venta', venta_id=venta_id))

# -------------------------------------------------------------
# RUTA DE BALANCE Y EXPORTACIÓN CONSOLIDADA
# -------------------------------------------------------------

@app.route('/balance', methods=['GET'])
@login_required
def ver_balance():
    """Calcula y muestra el balance y los reportes financieros."""
    conn = db_connector()
    if conn is None:
        flash("Error de conexión a la base de datos.", 'danger')
        return redirect(url_for('dashboard'))
    cursor = conn.cursor()
    
    # 1. CÁLCULO DE INGRESOS (Total de Ventas)
    cursor.execute("SELECT SUM(total) FROM ventas WHERE estado = 1")
    ingresos_result = cursor.fetchone()[0]
    ingresos = ingresos_result if ingresos_result is not None else 0.0
    
    # 2. CÁLCULO DEL COSTO DE LOS PRODUCTOS VENDIDOS (CPV)
    cursor.execute("""
        SELECT SUM(dv.cantidad * p.costo) 
        FROM detalles_venta dv
        JOIN productos p ON dv.producto_id = p.id
    """)
    cpv_result = cursor.fetchone()[0]
    costo_productos_vendidos = cpv_result if cpv_result is not None else 0.0

    # 3. CÁLCULO DE LA GANANCIA BRUTA
    ganancia_bruta = float(ingresos) - float(costo_productos_vendidos)

    # 4. Obtener las 5 ventas más recientes
    cursor.execute("""
        SELECT v.id, v.fecha, v.total, c.nombre, c.apellido
        FROM ventas v
        JOIN clientes c ON v.cliente_id = c.id
        ORDER BY v.fecha DESC
        LIMIT 5
    """)
    ventas_recientes = cursor.fetchall()
    
    conn.close()
    
    metricas_balance = {
        'ingresos': float(ingresos),
        'cpv': float(costo_productos_vendidos),
        'ganancia': ganancia_bruta
    }

    return render_template('balance.html', metricas=metricas_balance, ventas_recientes=ventas_recientes)
    

@app.route('/exportar_reporte_consolidado')
@login_required
def exportar_reporte_consolidado():
    """
    Exporta un archivo XLSX consolidado con formato profesional, incluyendo 
    Balance, Clientes, Productos, Ventas y Promociones.
    """
    conn = None
    try:
        conn = db_connector()
        cursor = conn.cursor()
        
        # --- 1. CÁLCULO DEL BALANCE (KPIs) ---
        cursor.execute("SELECT IFNULL(SUM(total), 0.00) FROM ventas WHERE estado = 1")
        ingresos = cursor.fetchone()[0] 

        cursor.execute("""
            SELECT IFNULL(SUM(dv.cantidad * p.costo), 0.00) 
            FROM detalles_venta dv
            JOIN productos p ON dv.producto_id = p.id
        """)
        costo_productos_vendidos = cursor.fetchone()[0]

        ganancia_bruta = float(ingresos) - float(costo_productos_vendidos)

        # CREAR DATAFRAME DEL BALANCE
        balance_data = {
            'Métrica': ['Total Ingresos (Ventas Activas)', 'Costo Productos Vendidos (CPV)', 'GANANCIA BRUTA'],
            'Valor': [float(ingresos), float(costo_productos_vendidos), ganancia_bruta]
        }
        df_balance = pd.DataFrame(balance_data)

        # --- 2. DEFINIR CONSULTAS Y ESTRUCTURA DE DATOS PARA DATOS TABULARES ---
        
        report_data = {
            'Clientes': (
                "SELECT id, nombre, apellido, email, telefono, direccion, fecha_registro FROM clientes",
                ['ID', 'Nombre', 'Apellido', 'Email', 'Teléfono', 'Dirección', 'Fecha Registro']
            ),
            'Productos': (
                "SELECT id, nombre, precio, costo, stock, codigo_barra FROM productos",
                ['ID', 'Nombre', 'Precio Venta', 'Costo', 'Stock', 'Código Barra']
            ),
            'Ventas': (
    """
    SELECT v.id,
           v.fecha,
           CONCAT(c.nombre, ' ', c.apellido) AS cliente,
           v.total,
           v.metodo_pago,
           u.nombre AS vendedor,
           v.estado
    FROM ventas v
    LEFT JOIN clientes c ON v.cliente_id = c.id
    LEFT JOIN usuarios u ON v.usuario_id = u.id
    ORDER BY v.fecha DESC
    """,
    ['ID Venta', 'Fecha', 'Cliente', 'Total', 'Método Pago', 'Vendedor', 'Estado']
),

            'Promociones': (
                "SELECT id, nombre, valor, activo, fecha_inicio, fecha_fin FROM promociones",
                ['ID', 'Nombre', 'Valor (%)', 'Activa', 'Fecha Inicio', 'Fecha Fin']
            )
        }
        
        # --- 3. CREAR DICCIONARIO DE DATAFRAMES (INCLUYENDO BALANCE PRIMERO) ---
        dfs = {'Balance Resumen': df_balance}
        for sheet_name, (query, columns) in report_data.items():
            cursor.execute(query)
            data = cursor.fetchall()
            dfs[sheet_name] = pd.DataFrame(data, columns=columns)

        # --- 4. GENERAR ARCHIVO EXCEL EN MEMORIA CON FORMATO ---
        output = BytesIO() 
        
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            
            workbook = writer.book
            
            # --- DEFINICIÓN DE FORMATOS GLOBALES ---
            header_format = workbook.add_format({
                'bold': True, 'text_wrap': True, 'valign': 'vcenter',
                'align': 'center', 'fg_color': '#D9E1F2', 'border': 1
            })

            currency_format = workbook.add_format({'num_format': '$#,##0.00'})
            center_format = workbook.add_format({'align': 'center'})
            bold_format = workbook.add_format({'bold': True})
            
            # Formato especial para la Ganancia Bruta (Resaltado)
            ganancia_format = workbook.add_format({
                'bold': True, 'num_format': '$#,##0.00',
                'bg_color': '#D0F0C0', # Verde claro
                'border': 1
            })

            # --- APLICAR FORMATOS A CADA HOJA ---
            for sheet_name, df in dfs.items():
                
                df.to_excel(writer, sheet_name=sheet_name, index=False)
                worksheet = writer.sheets[sheet_name]
                
                # --- MANEJO ESPECIAL PARA LA HOJA DE BALANCE ---
                if sheet_name == 'Balance Resumen':
                    
                    # Anchos de columna
                    worksheet.set_column('A:A', 35, bold_format)
                    worksheet.set_column('B:B', 20)
                    
                    # Aplicar formato de encabezado a Métrica y Valor
                    worksheet.set_row(0, 20, header_format) 

                    # Aplicar formato de moneda a las filas de valores
                    worksheet.write(1, 1, df['Valor'].iloc[0], currency_format)
                    worksheet.write(2, 1, df['Valor'].iloc[1], currency_format)
                    
                    # Resaltar la GANANCIA BRUTA (fila 3)
                    worksheet.write(3, 0, df['Métrica'].iloc[2], ganancia_format)
                    worksheet.write(3, 1, df['Valor'].iloc[2], ganancia_format)
                    
                    continue # Salta el formato genérico

                # --- MANEJO GENÉRICO PARA HOJAS TABULARES ---
                
                # 1. Aplicar el formato de encabezado centrado
                worksheet.set_row(0, 20, header_format) 
                
                # 2. Ajustar el ancho y aplicar formato de datos
                for col_num, col_name in enumerate(df.columns):
                    # Calcula la longitud máxima de la columna o nombre, +2 para padding
                    max_len = max(df[col_name].astype(str).map(len).max(), len(col_name)) + 2
                    
                    # Aplicar formatos específicos
                    if col_name in ['Precio Venta', 'Costo', 'Total']:
                        # Columna de precio y total (ancho y moneda)
                        worksheet.set_column(col_num, col_num, max_len, currency_format)
                    elif col_name in ['ID', 'ID Venta', 'Stock', 'Valor (%)', 'Activa', 'Estado']:
                        # Columnas centradas
                        worksheet.set_column(col_num, col_num, max_len, center_format)
                    else:
                        # Resto de columnas (texto general)
                        worksheet.set_column(col_num, col_num, max_len)

            
        output.seek(0)

        # --- 5. ENVIAR ARCHIVO ---
        return send_file(
            output,
            download_name=f"Reporte_Consolidado_NYJ_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
            as_attachment=True,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        
    except Exception as e:
        flash(f'Error al exportar el reporte consolidado: {e}', 'danger')
        print(f'Error al exportar el reporte consolidado: {e}')
        return redirect(url_for('ver_balance'))
    finally:
        if conn and conn.is_connected():
            conn.close()

# -------------------------------------------------------------------
# RUTAS DE PROMOCIONES
# -------------------------------------------------------------------

@app.route('/promociones')
def listar_promociones():
    conn = db_connector()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("""
        SELECT id, nombre, tipo, valor,
               fecha_inicio, fecha_fin, activo
        FROM promociones
    """)

    promociones = cursor.fetchall()
    conn.close()

    return render_template("promociones.html", promociones=promociones)



@app.route('/promociones/estado/<int:promo_id>', methods=['POST'])
def alternar_estado_promocion(promo_id):
    conn = db_connector()
    cursor = conn.cursor()

    cursor.execute("""
       UPDATE promociones SET activo = 0 WHERE id = %s
        SET activo = NOT activo
        WHERE id = %s
    """, (promo_id,))

    conn.commit()
    cursor.close()
    conn.close()

    flash("Estado de la promoción actualizado.", "success")
    return redirect(url_for('listar_promociones'))




@app.route('/promociones/crear', methods=['POST'])
def crear_promocion():
    nombre = request.form['nombre']
    descripcion = request.form.get('descripcion')
    tipo = request.form['tipo']
    valor = request.form['valor']
    fecha_inicio = request.form['fecha_inicio']
    fecha_fin = request.form['fecha_fin']
    activo = 1 if request.form.get('activo') else 0

    conn = db_connector()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO promociones 
        (nombre, descripcion, tipo, valor, fecha_inicio, fecha_fin, activo)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
    """, (nombre, descripcion, tipo, valor, fecha_inicio, fecha_fin, activo))

    conn.commit()
    conn.close()

    flash("Promoción creada correctamente", "success")
    return redirect(url_for('listar_promociones'))



@app.route('/promociones/editar/<int:id>')
@login_required
def ver_promocion(id):
    try:
        conn = db_connector()
        cursor = conn.cursor(dictionary=True)
        # Asegúrate de seleccionar todos los campos necesarios
        cursor.execute("SELECT id, nombre, tipo_valor, inicio, fin, estado, registro FROM promociones WHERE id = %s", (id,)) 
        promocion = cursor.fetchone()
        conn.close()

        if promocion:
            return render_template('promociones/editar_promocion.html', promocion=promocion)
        else:
            flash("Promoción no encontrada.", "danger")
            # ⚠️ CORRECCIÓN DE RUTA
            return redirect(url_for('listar_promociones')) 
            
    except Exception as e:
        # Se incluye la importación aquí para mayor claridad en el código
        from mysql.connector.errors import ProgrammingError
        if isinstance(e, ProgrammingError):
             # Este error ocurre si la tabla 'promociones' no tiene la columna 'registro'
             flash("Error en la estructura de la base de datos (columna 'registro' faltante o error en SELECT).", "danger")
        else:
             flash(f"Ocurrió un error inesperado: {e}", "danger")
        
        # ⚠️ CORRECCIÓN DE RUTA
        return redirect(url_for('listar_promociones'))

# --- RUTAS DE EDICIÓN Y ELIMINACIÓN ---
@app.route('/promociones/editar/<int:promo_id>', methods=['GET', 'POST'])
def editar_promocion(promo_id):
    conn = db_connector()
    cursor = conn.cursor(dictionary=True)

    if request.method == 'POST':
        cursor.execute("""
            UPDATE promociones
            SET nombre=%s, tipo=%s, valor=%s, fecha_inicio=%s, fecha_fin=%s, estado=%s
            WHERE id=%s
        """, (
            request.form['nombre'],
            request.form['tipo'],
            request.form['valor'],
            request.form['fecha_inicio'],
            request.form['fecha_fin'],
            request.form['estado'],
            promo_id
        ))
        conn.commit()
        conn.close()
        flash("Promoción actualizada", "success")
        return redirect(url_for('listar_promociones'))

    cursor.execute("SELECT * FROM promociones WHERE id=%s", (promo_id,))
    promo = cursor.fetchone()
    conn.close()

    return render_template("editar_promocion.html", promo=promo)


@app.route('/actualizar_promocion/<int:id>', methods=['POST'])
@login_required
def actualizar_promocion(id):
    if request.method == 'POST':
        nombre = request.form['nombre']
        tipo_valor = request.form['tipo_valor']
        inicio = request.form['inicio']
        fin = request.form['fin']
        
        # ⚠️ CORRECCIÓN ESTADO: Convierte el valor del checkbox a 1 o 0
        # Si el checkbox está marcado, request.form.get('estado') es 'on'. Si no, es None.
        estado = 1 if request.form.get('estado') == 'on' else 0
        
        # ⚠️ CORRECCIÓN REGISTRO: Genera la fecha y hora actual (Fecha de última actualización)
        registro = datetime.now() 
        
        try:
            conn = db_connector()
            cursor = conn.cursor()
            
            sql = """
                UPDATE promociones 
                SET nombre=%s, tipo_valor=%s, inicio=%s, fin=%s, estado=%s, registro=%s 
                WHERE id=%s
            """
            
            data = (nombre, tipo_valor, inicio, fin, estado, registro, id)
            
            cursor.execute(sql, data)
            conn.commit()
            conn.close()
            
            flash('Promoción actualizada exitosamente.', 'success')
            # ⚠️ CORRECCIÓN DE RUTA
            return redirect(url_for('listar_promociones'))

        except Exception as e:
            flash(f"Error al actualizar la promoción: {e}", "danger")
            # ⚠️ CORRECCIÓN DE RUTA
            return redirect(url_for('listar_promociones'))
    
    # ⚠️ CORRECCIÓN DE RUTA
    return redirect(url_for('listar_promociones'))

@app.route('/promociones/eliminar/<int:promo_id>', methods=['POST'])
def eliminar_promocion(promo_id):
    conn = db_connector()
    cursor = conn.cursor()

    cursor.execute("DELETE FROM promociones WHERE id=%s", (promo_id,))
    conn.commit()
    conn.close()

    flash("Promoción eliminada", "success")
    return redirect(url_for('listar_promociones'))

# -------------------------------------------------------------------
# EJECUCIÓN DEL SERVIDOR
# -------------------------------------------------------------------
if __name__ == '__main__':
    # El host='0.0.0.0' permite acceder desde otras máquinas en la red local
    app.run(debug=True)