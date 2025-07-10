
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, filters,
    ContextTypes, ConversationHandler, CallbackQueryHandler
)
import os
from datetime import datetime, time, timedelta
from apscheduler.schedulers.background import BackgroundScheduler
import re

# Estaciones en orden
ESTACIONES = [
    "preparado", "componentes", "taponeo", "ensamble", "clivado", "crimpado",
    "pulido", "limpieza", "geometria", "armado", "etiquetas", "prueba"
]

# Estados del bot
PEDIR_HORA, REGISTRAR_PUNTAS = range(2)

produccion_diaria = {}

# /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("¿De qué horario ingresaremos las puntas?")
    return PEDIR_HORA

# Al hacer clic en el botón
async def boton_iniciar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.message.reply_text("¿De qué horario ingresaremos las puntas?")
    context.user_data["hora"] = None
    context.user_data["estacion_index"] = 0
    context.user_data["resultados"] = {}
    return PEDIR_HORA

# Recibe la hora
async def recibir_hora(update: Update, context: ContextTypes.DEFAULT_TYPE):
    hora = update.message.text.strip().lower()
    if not re.match(r"\d+\s*[ap]m", hora):
        await update.message.reply_text("❌ Formato inválido. Usa por ejemplo: 7 am")
        return PEDIR_HORA

    context.user_data["hora"] = hora.replace(" ", "")
    context.user_data["estacion_index"] = 0
    context.user_data["resultados"] = {}

    estacion_actual = ESTACIONES[0]
    await update.message.reply_text(f"Ingresaremos puntas de las {hora} de {estacion_actual}.\n¿Cuánto produjo?")
    return REGISTRAR_PUNTAS

# Registra producción
async def registrar_puntas(update: Update, context: ContextTypes.DEFAULT_TYPE):
    entrada = update.message.text.strip()

    try:
        if "*" in entrada:
            partes = entrada.split("*")
            bobinas = [int(x) for x in partes[0].split()]
            piezas_por_bobina = int(partes[1].strip())
            cantidad_bobinas = sum(bobinas)
            total = cantidad_bobinas * piezas_por_bobina
            mensaje_registro = f"{cantidad_bobinas} bobinas registradas en {ESTACIONES[context.user_data['estacion_index']]}, total: {total} puntas."
        else:
            total = sum(int(x) for x in entrada.split())
            mensaje_registro = f"{total} puntas registradas en {ESTACIONES[context.user_data['estacion_index']]}."
    except:
        await update.message.reply_text("❌ Formato inválido. Usa solo números separados por espacios o con multiplicador. Ej: 10 10 10 * 2")
        return REGISTRAR_PUNTAS

    estacion_index = context.user_data["estacion_index"]
    estacion_actual = ESTACIONES[estacion_index]
    hora = context.user_data["hora"]
    fecha = datetime.now().strftime("%Y-%m-%d")

    context.user_data["resultados"][estacion_actual] = total

    if fecha not in produccion_diaria:
        produccion_diaria[fecha] = {}
    if hora not in produccion_diaria[fecha]:
        produccion_diaria[fecha][hora] = {}

    produccion_diaria[fecha][hora][estacion_actual] = total

    await update.message.reply_text(mensaje_registro)

    # Avanzar a la siguiente estación
    estacion_index += 1
    if estacion_index >= len(ESTACIONES):
        await update.message.reply_text(f"✅ Todas las estaciones fueron registradas para las {hora}.")
        return ConversationHandler.END
    else:
        context.user_data["estacion_index"] = estacion_index
        siguiente = ESTACIONES[estacion_index]
        await update.message.reply_text(f"¿Cuánto produjo {siguiente}?")
        return REGISTRAR_PUNTAS

# /reporte 7am
async def reporte(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) != 1:
        await update.message.reply_text("❌ Usa el comando así: /reporte 7am")
        return

    hora = context.args[0].lower()
    fecha = datetime.now().strftime("%Y-%m-%d")

    if fecha not in produccion_diaria or hora not in produccion_diaria[fecha]:
        await update.message.reply_text(f"No hay datos registrados para las {hora}.")
        return

    datos = produccion_diaria[fecha][hora]
    mensaje = f"📊 Producción para las {hora} del {fecha}:\n"
    for estacion, cantidad in datos.items():
        mensaje += f"• {estacion}: {cantidad}\n"
    await update.message.reply_text(mensaje)

# /reporte_total
async def reporte_total(update: Update, context: ContextTypes.DEFAULT_TYPE):
    fecha = datetime.now().strftime("%Y-%m-%d")

    if fecha not in produccion_diaria:
        await update.message.reply_text("No hay datos registrados hoy.")
        return

    acumulado = {estacion: 0 for estacion in ESTACIONES}
    for hora in produccion_diaria[fecha].values():
        for estacion, cantidad in hora.items():
            acumulado[estacion] += cantidad

    mensaje = f"📈 Total acumulado del día {fecha}:\n"
    for estacion, total in acumulado.items():
        mensaje += f"• {estacion}: {total}\n"
    await update.message.reply_text(mensaje)

# Cancelar
async def cancelar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("⛔ Registro cancelado.")
    return ConversationHandler.END

# ⏰ Recordatorio cada hora
async def enviar_recordatorio(context: ContextTypes.DEFAULT_TYPE):
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    boton = InlineKeyboardMarkup([
        [InlineKeyboardButton("📤 Iniciar registro", callback_data="iniciar_registro")]
    ])
    hora_actual = datetime.now().strftime("%I:%M %p")
    await context.bot.send_message(chat_id=chat_id, text=f"⏰ Son las {hora_actual}. ¿Ya registraste las puntas?", reply_markup=boton)

# MAIN
if __name__ == "__main__":
    import dotenv
    dotenv.load_dotenv()

    TOKEN = os.getenv("TELEGRAM_TOKEN")
    app = ApplicationBuilder().token(TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            PEDIR_HORA: [MessageHandler(filters.TEXT & ~filters.COMMAND, recibir_hora)],
            REGISTRAR_PUNTAS: [MessageHandler(filters.TEXT & ~filters.COMMAND, registrar_puntas)],
        },
        fallbacks=[CommandHandler("cancelar", cancelar)],
    )

    app.add_handler(conv_handler)
    app.add_handler(CommandHandler("reporte", reporte))
    app.add_handler(CommandHandler("reporte_total", reporte_total))
    app.add_handler(CallbackQueryHandler(boton_iniciar, pattern="^iniciar_registro$"))

    scheduler = BackgroundScheduler()
    hora = time(8, 0)
    while hora <= time(18, 30):
        scheduler.add_job(enviar_recordatorio, 'cron', hour=hora.hour, minute=hora.minute, args=[app])
        hora = (datetime.combine(datetime.today(), hora) + timedelta(hours=1)).time()
    scheduler.start()

    print("Bot corriendo...")
    app.run_polling()
