import os
import pandas as pd
from groq import Groq
from datetime import datetime, timedelta
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# ===================== CONFIGURACIÓN =====================
load_dotenv()

GROQ_API_KEY    = os.getenv("GROQ_API_KEY")
TELEGRAM_TOKEN  = os.getenv("TELEGRAM_TOKEN")

GROQ_MODEL               = "llama-3.3-70b-versatile"  # Cambia según el modelo que prefieras
TIEMPO_EXPIRACION_MIN    = 60   # Minutos antes de reiniciar contexto
LIMITE_CONTEXTO          = 5    # Número de intercambios anteriores a incluir
HISTORIAL_EXCEL          = "historial_conversaciones.xlsx"
COLUMNAS                 = ["ID Usuario", "Nombre Usuario", "Fecha y Hora", "Pregunta", "Respuesta"]

cliente = Groq(api_key=GROQ_API_KEY)


# ===================== EXCEL =====================
def asegurar_excel() -> None:
    """Crea el archivo Excel si no existe o si le faltan columnas."""
    if not os.path.exists(HISTORIAL_EXCEL):
        pd.DataFrame(columns=COLUMNAS).to_excel(HISTORIAL_EXCEL, index=False)
        return
    try:
        df = pd.read_excel(HISTORIAL_EXCEL)
        if not all(col in df.columns for col in COLUMNAS):
            pd.DataFrame(columns=COLUMNAS).to_excel(HISTORIAL_EXCEL, index=False)
    except Exception:
        pd.DataFrame(columns=COLUMNAS).to_excel(HISTORIAL_EXCEL, index=False)


def cargar_historial() -> pd.DataFrame:
    asegurar_excel()
    df = pd.read_excel(HISTORIAL_EXCEL)
    df["Fecha y Hora"] = pd.to_datetime(df["Fecha y Hora"], errors="coerce")
    return df


def registrar_en_excel(user_id: str, nombre: str, pregunta: str, respuesta: str) -> None:
    nuevo = pd.DataFrame([{
        "ID Usuario":    user_id,
        "Nombre Usuario": nombre,
        "Fecha y Hora":  datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "Pregunta":      pregunta,
        "Respuesta":     respuesta,
    }])
    historial = cargar_historial()
    pd.concat([historial, nuevo], ignore_index=True).to_excel(HISTORIAL_EXCEL, index=False)


# ===================== CONTEXTO =====================
def obtener_contexto(usuario_id: str, historial: pd.DataFrame) -> str:
    """
    Devuelve las últimas N interacciones del usuario.
    Retorna cadena vacía si el último mensaje fue hace más de TIEMPO_EXPIRACION_MIN.
    """
    hist_usuario = historial[historial["ID Usuario"].astype(str) == str(usuario_id)]
    if hist_usuario.empty:
        return ""

    ultima_fecha = hist_usuario["Fecha y Hora"].max()
    if pd.isnull(ultima_fecha):
        return ""

    if datetime.now() - ultima_fecha > timedelta(minutes=TIEMPO_EXPIRACION_MIN):
        return ""   # Contexto expirado → conversación nueva

    recientes = hist_usuario.tail(LIMITE_CONTEXTO)
    return "\n".join(
        f"Usuario: {r['Pregunta']}\nAsistente: {r['Respuesta']}"
        for _, r in recientes.iterrows()
    )


# ===================== GROQ =====================
def consultar_groq(contexto: str, pregunta: str) -> str:
    """Arma el prompt y llama a la API de Groq."""
    system_prompt = (
        "Eres un asistente virtual del emprendimiento jugos naturales FRUCTIFEROS, Maria Clara ."
        "Responde de forma clara, formal y concisa , sera un plaser atenderte, hoy tenemos jugos de: jugos de corozo y"
        "Maracuya 16 onzas---- $3000"
        "Maracuya 9 onzas... $2000"
        "Jugo de mango 9 onzas.....$1500"
        "Jugo de zanahoria 16 onzas....$2500"
        "Jugo de piña 16 onzas.....$2500"
         "Jugo de Piña 9 onzas.... $1500"
        "- Elaborados con ingredientes frescos y naturales . Por favor indicanos sabor de jugo,  Tamaño 9 ó 16 onzas-"
        "Cantidad que deseas ordenar. Estaremos encantados de preparar tu pedido- ¡Cúal  sabor te gustaria ordenar hoy y"
        " para cerrar la venta: pedido registrado con exito. Gracias por elegir jugos FRUCTIFEROS, Maria "
       "¡Qué sabor te gustaria ordenar hoy?  . y para cerrar la venta ¡Pedido registrado con exito¡ Gracias por elegir"
        "Jugos FRUCTIFEROS Maria Clara. agradecemos tu compra y esperamos atenderte   nuevamente"
        "Medios de pago: Efectivo, Transferencias Nequi o Bre-Be"
        "Si es Nequi o Bre-be haga la transferencia al numero 3103281341 Maria Clara del Risco"
        "Cuando realice el pago favor enviar soporte"
        "Si es envio a domicilio enviar la direccion"
    
    )

    mensajes = [{"role": "system", "content": system_prompt}]

    # Inyectar contexto como turnos previos de la conversación
    if contexto:
        for linea in contexto.strip().split("\n"):
            if linea.startswith("Usuario: "):
                mensajes.append({"role": "user",      "content": linea[len("Usuario: "):]})
            elif linea.startswith("Asistente: "):
                mensajes.append({"role": "assistant", "content": linea[len("Asistente: "):]})

    mensajes.append({"role": "user", "content": pregunta})

    respuesta = cliente.chat.completions.create(
        model=GROQ_MODEL,
        messages=mensajes,
        max_tokens=512,
        temperature=0.4,
    )
    return respuesta.choices[0].message.content.strip()


# ===================== HANDLERS TELEGRAM =====================
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        " Bienvenido al asistente virtual de Jugos Naturales FRUCTIFEROS.\n"
        "En que podemos servirle?."
    )


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        " *Comandos disponibles:*\n"
        "/start — Inicia el bot\n"
        "/help  — Muestra esta ayuda\n\n"
        "Simplemente el servicio que deseas.",
        parse_mode="Markdown",
    )


async def responder(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id  = str(update.message.from_user.id)
    nombre   = update.message.from_user.first_name or "Usuario"
    pregunta = update.message.text.strip()

    if not pregunta:
        return

    historial = cargar_historial()
    contexto  = obtener_contexto(user_id, historial)

    try:
        texto = consultar_groq(contexto, pregunta)
    except Exception as e:
        texto = f" Error al procesar la consulta: {e}"

    registrar_en_excel(user_id, nombre, pregunta, texto)
    await update.message.reply_text(texto)


# ===================== MAIN =====================
def main() -> None:
    if not GROQ_API_KEY or not TELEGRAM_TOKEN:
        raise ValueError("Faltan variables de entorno: GROQ_API_KEY y/o TELEGRAM_TOKEN")

    asegurar_excel()

    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help",  cmd_help))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, responder))

    print(" Asistente FRUCTIFEROS ejecutándose... Ctrl+C para detener.")
    app.run_polling()


if __name__ == "__main__":
    main()
