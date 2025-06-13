import requests
import logging
import base64
import os
from dotenv import load_dotenv
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

load_dotenv()

# URLs de la API
API_URL_PRODUCTS = os.getenv("API_URL_PRODUCTS")
API_URL_CATEGORIES = os.getenv("API_URL_CATEGORIES")

# Caché simple en memoria para evitar peticiones repetidas
cache = {
    "products": {"data": None, "timestamp": None},
    "categories": {"data": None, "timestamp": None},
}
CACHE_TTL = timedelta(minutes=15)

def _process_product_images(products):
    """
    Función interna para decodificar y cachear imágenes de productos en memoria.
    """
    if not products:
        return []
    
    for product in products:
        product['_image_bytes'] = None 
        if product.get('images') and product['images'][0].get('imageData'):
            try:
                base64_string = product['images'][0]['imageData'].split(',')[1]
                image_bytes = base64.b64decode(base64_string)
                product['_image_bytes'] = image_bytes
            except Exception as e:
                logger.error(f"Error decodificando imagen para producto {product['id']} durante el procesamiento: {e}")
    return products

def get_data_from_api(data_type):
    """
    Función genérica para obtener datos desde la API, usando caché y pre-procesando imágenes.
    """
    if data_type not in cache:
        return None

    now = datetime.now()
    if cache[data_type]["data"] and (now - cache[data_type]["timestamp"]) < CACHE_TTL:
        logger.info(f"Usando caché para '{data_type}'")
        return cache[data_type]["data"]

    url = API_URL_PRODUCTS if data_type == "products" else API_URL_CATEGORIES
    try:
        logger.info(f"Haciendo petición a la API para '{data_type}'...")
        response = requests.get(url, timeout=15)
        response.raise_for_status()
        
        data = response.json()

        if data_type == "products":
            logger.info("Pre-procesando imágenes de productos...")
            data = _process_product_images(data)
            logger.info("Imágenes pre-procesadas y listas en memoria.")
        
        cache[data_type]["data"] = data
        cache[data_type]["timestamp"] = now
        logger.info(f"Caché actualizado para '{data_type}'")
        
        return data
    except requests.exceptions.RequestException as e:
        logger.error(f"Error al obtener datos de la API para '{data_type}': {e}")
        return None

def get_products():
    """Obtiene la lista de todos los productos (con imágenes ya procesadas)."""
    return get_data_from_api("products")

def get_categories():
    """Obtiene la lista de todas las categorías."""
    return get_data_from_api("categories")

def get_product_by_id(product_id):
    """Obtiene un producto específico por su ID."""
    products = get_products()
    if not products:
        return None
    
    for product in products:
        if product['id'] == product_id:
            return product
    return None
