import os
import sys
import logging
import io
from dotenv import load_dotenv
from flask import Flask, request
import telebot
from telebot import types

# cliente de API
import api_client

# ========== Configuración Inicial ==========
app = Flask(__name__)
logger = logging.getLogger(__name__)

# ==========  Flask routes ==========
@app.route('/')
def health_check():
    return "🤖 Bot activo", 200

@app.route('/webhook', methods=['POST'])
def webhook():
    if request.headers.get('content-type') == 'application/json':
        json_string = request.get_data().decode('utf-8')
        update = telebot.types.Update.de_json(json_string)
        bot.process_new_updates([update])
        return '', 200
    return 'Invalid content type', 403

# ========== Configuración del Bot ==========
load_dotenv()
BOT_TOKEN = str(os.getenv("BOT_TOKEN"))
WEBHOOK_URL = str(os.getenv("WEBHOOK_URL"))

bot = telebot.TeleBot(str(BOT_TOKEN), parse_mode="HTML")

# Constantes
PRODUCTS_PER_PAGE = 8
PLACEHOLDER_IMAGE_PATH = 'placeholder.jpg'

# ========== Funciones de Lógica del Catálogo ==========

def format_product_details(product):
    """Formatea los detalles de un producto y prepara la imagen ya decodificada."""
    photo_stream = io.BytesIO(product['_image_bytes']) if product.get('_image_bytes') else None
    caption = (
        f"<b>{product['name']}</b>\n\n"
        f"<b>Categoría:</b> {product['category']}\n"
        f"<b>Marca:</b> {product['brand']}\n"
        f"<b>Precio:</b> ${product['price']}\n"
        f"<b>Stock:</b> {product['stock']} unidades\n"
        f"<i>Ofertado por: {product['seller']}</i>"
    )
    return photo_stream, caption

def show_product_details(chat_id, product_id, message_id):
    """Muestra el detalle del producto, siempre editando el mensaje de media existente."""
    product = api_client.get_product_by_id(int(product_id))
    if not product:
        return False

    photo_stream, caption = format_product_details(product)
    
    # Navegación
    all_products = api_client.get_products()
    product_ids = [p['id'] for p in all_products]
    try:
        current_index = product_ids.index(int(product_id))
    except ValueError:
        return False

    markup = types.InlineKeyboardMarkup()
    nav_buttons = []
    if current_index > 0:
        prev_id = product_ids[current_index - 1]
        nav_buttons.append(types.InlineKeyboardButton("⬅️ Anterior", callback_data=f"product:id:{prev_id}"))
    if current_index < len(product_ids) - 1:
        next_id = product_ids[current_index + 1]
        nav_buttons.append(types.InlineKeyboardButton("Siguiente ➡️", callback_data=f"product:id:{next_id}"))
    
    markup.row(*nav_buttons)
    markup.add(types.InlineKeyboardButton("↩️ Volver a Categorías", callback_data="show_categories"))

    # Lógica segura para manejar la imagen
    photo_to_use = photo_stream if photo_stream else open(PLACEHOLDER_IMAGE_PATH, 'rb')
    media = types.InputMediaPhoto(photo_to_use, caption=caption, parse_mode="HTML")
    
    try:
        bot.edit_message_media(media=media, chat_id=chat_id, message_id=message_id, reply_markup=markup)
    except Exception as e:
        logger.error(f"Error al editar detalle de producto: {e}")
    finally:
        # Si abrimos el placeholder, nos aseguramos de cerrarlo.
        if photo_to_use is not photo_stream:
            photo_to_use.close()

def show_paginated_products(chat_id, message_id, page=0, category_id=None):
    """Muestra una lista paginada de productos, siempre editando el mensaje de media."""
    products = api_client.get_products()
    if not products:
        return False

    category_name = "Todos los Productos"
    filtered_products = products
    if category_id:
        categories = api_client.get_categories()
        category_name = next((c['name'] for c in categories if c['id'] == category_id), "Desconocida")
        filtered_products = [p for p in products if p['category'] == category_name]

    if not filtered_products:
        caption = f"📦 No hay productos en la categoría: <b>{category_name}</b>"
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("↩️ Volver a Categorías", callback_data="show_categories"))
        bot.edit_message_caption(caption, chat_id, message_id, reply_markup=markup)
        return

    start, end = page * PRODUCTS_PER_PAGE, (page + 1) * PRODUCTS_PER_PAGE
    products_on_page = filtered_products[start:end]

    caption = f"<b>Catálogo: {category_name}</b> (Página {page + 1})\n\n"
    markup = types.InlineKeyboardMarkup(row_width=1)
    for product in products_on_page:
        markup.add(types.InlineKeyboardButton(product['name'], callback_data=f"product:id:{product['id']}"))

    pagination_buttons = []
    cb_prefix = f"category:id:{category_id}" if category_id else "products"
    if start > 0:
        pagination_buttons.append(types.InlineKeyboardButton("⬅️ Anterior", callback_data=f"{cb_prefix}:page:{page-1}"))
    if end < len(filtered_products):
        pagination_buttons.append(types.InlineKeyboardButton("Siguiente ➡️", callback_data=f"{cb_prefix}:page:{page+1}"))
    
    markup.row(*pagination_buttons)
    markup.add(types.InlineKeyboardButton("↩️ Volver a Categorías", callback_data="show_categories"))
    
    # Manejo seguro del archivo placeholder
    with open(PLACEHOLDER_IMAGE_PATH, 'rb') as placeholder_photo:
        media = types.InputMediaPhoto(placeholder_photo, caption=caption, parse_mode="HTML")
        try:
            bot.edit_message_media(media=media, chat_id=chat_id, message_id=message_id, reply_markup=markup)
        except Exception as e:
            logger.warning(f"No se pudo editar el mensaje a lista (posiblemente no cambió): {e}")

def send_categories_list(chat_id, message_id=None):
    """Muestra el menú de categorías. Envía un nuevo mensaje o edita uno existente."""
    all_categories = api_client.get_categories()
    all_products = api_client.get_products()

    if not all_categories or not all_products:
        bot.send_message(chat_id, "❌ No se pudieron obtener los datos del catálogo en este momento.")
        return
        
    # Filtra para mostrar solo categorías que tienen productos
    product_categories_names = {p['category'] for p in all_products}
    categories = [cat for cat in all_categories if cat['name'] in product_categories_names and cat.get('is_active', 1)]

    if not categories:
        caption = "😕 No hay categorías con productos disponibles en este momento."
        markup = types.InlineKeyboardMarkup() # Un markup vacío
    else:
        caption = "👇 <b>Selecciona una categoría</b> para ver los productos o explora el catálogo completo."
        markup = types.InlineKeyboardMarkup(row_width=2)
        buttons = [types.InlineKeyboardButton(c['name'], callback_data=f"category:id:{c['id']}:page:0") for c in categories]
        markup.add(*buttons)
        markup.add(types.InlineKeyboardButton("➡️ Ver todos los productos", callback_data="products:page:0"))

    # Manejo seguro del archivo, tanto para editar como para enviar nuevo
    with open(PLACEHOLDER_IMAGE_PATH, 'rb') as placeholder_photo:
        if message_id:
            media = types.InputMediaPhoto(placeholder_photo, caption=caption, parse_mode="HTML")
            bot.edit_message_media(media=media, chat_id=chat_id, message_id=message_id, reply_markup=markup)
        else:
            bot.send_photo(chat_id, photo=placeholder_photo, caption=caption, reply_markup=markup)

# ========== Manejadores del Bot ==========
def setup_bot_handlers():
    bot.set_my_commands([
        telebot.types.BotCommand("/start", "Iniciar el bot"),
        telebot.types.BotCommand("/catalogo", "Ver el catálogo de productos"),
        telebot.types.BotCommand("/help", "Mostrar ayuda"),
    ])

    @bot.message_handler(commands=["start", "help"])
    def send_welcome(message):
        text = (
            "¡Bienvenido a <b>Carfix Bot</b>! 🚗\n\n"
            "Usa el comando /catalogo para explorar nuestros repuestos de forma interactiva.\n\n"
            "<b>Comandos:</b>\n"
            "/start - Muestra este mensaje de bienvenida.\n"
            "/catalogo - Abre el menú principal del catálogo.\n"
            "/help - Muestra esta ayuda."
        )
        bot.reply_to(message, text)

    @bot.message_handler(commands=["catalogo"])
    def send_catalog_menu(message):
        send_categories_list(message.chat.id)

    @bot.callback_query_handler(func=lambda call: True)
    def callback_handler(call):
        bot.answer_callback_query(call.id)
        
        parts = call.data.split(':')
        command = parts[0]
        chat_id = call.message.chat.id
        message_id = call.message.message_id
        
        success = False
        try:
            if command == "products":
                page = int(parts[2])
                success = show_paginated_products(chat_id, message_id, page=page)
            
            elif command == "category":
                category_id, page = int(parts[2]), int(parts[4])
                success = show_paginated_products(chat_id, message_id, page=page, category_id=category_id)

            elif command == "product":
                product_id = int(parts[2])
                success = show_product_details(chat_id, product_id, message_id)
            
            elif command == "show_categories":
                send_categories_list(chat_id, message_id)
                success = True

            if not success:
                bot.answer_callback_query(call.id, text="❌ La acción falló. El producto o categoría podría no estar disponible.", show_alert=True)

        except Exception as e:
            logger.error(f"Error procesando callback '{call.data}': {e}", exc_info=True)
            bot.answer_callback_query(call.id, text="⚠️ Ocurrió un error inesperado.", show_alert=True)

# ========== Configuración de Logging y Flask ==========
def setup_logging():
    formatting = logging.Formatter('%(asctime)s | %(levelname)-8s | %(name)s | %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
    stream_logging = logging.StreamHandler(sys.stdout)
    stream_logging.setFormatter(formatting)
    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)
    logger.addHandler(stream_logging)
    logging.getLogger('telebot').setLevel(logging.INFO)
    logging.getLogger('urllib3').setLevel(logging.INFO)
    if os.environ.get('HOSTING') == "production":
        stream_logging.setLevel(logging.INFO)
    else:
        stream_logging.setLevel(logging.DEBUG)

# ========== Entry Point ==========
if __name__ == '__main__':
    setup_logging()
    setup_bot_handlers()

    if not os.path.exists(PLACEHOLDER_IMAGE_PATH):
        logger.error(f"FATAL: La imagen de placeholder '{PLACEHOLDER_IMAGE_PATH}' no fue encontrada.")
        sys.exit(1)
        
    if os.environ.get('HOSTING') == "production":
        from waitress import serve
        logger.info("Iniciando bot en modo PRODUCCIÓN con Webhook.")
        bot.remove_webhook()
        bot.set_webhook(url=WEBHOOK_URL + '/webhook')
        serve(app, host='0.0.0.0', port=os.environ.get('PORT', 8080))
    else:
        logger.info("Iniciando bot en modo DESARROLLO con Polling.")
        bot.remove_webhook()
        bot.infinity_polling()

