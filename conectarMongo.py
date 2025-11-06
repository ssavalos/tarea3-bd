from pymongo import MongoClient

# Dirección de conexión al Replica Set
connection_string = "mongodb://mongo1:30001,mongo2:30002,mongo3:30003/?replicaSet=my-replicaset&readPreference=primary&appname=MongoDB%20Compass&ssl=false"

# Crear cliente de MongoDB
client = MongoClient(connection_string)

# Verificar la conexión
try:
    # Obtener información del Replica Set
    print("Replica Set Name:", client.admin.command("ismaster")["setName"])
    print("Connected to MongoDB Replica Set successfully!")
except Exception as e:
    print("Error connecting to MongoDB Replica Set:", e)

# Ejemplo de acceso a una base de datos y colección
db = client.test_database
collection = db.test_collection

# Insertar un documento
collection.insert_one({"name": "Docker", "type": "Replica Set"})

# Leer documentos
for doc in collection.find():
    print(doc)
