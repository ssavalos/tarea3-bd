"""
Funciones principales:
1. --ingest: Calcula los embeddings del corpus DiscursosOriginales y los inserta en la
   coleccion Politica.Discursos.
2. --query: Recibe una consulta textual, calcula su embedding y entrega los 5 documentos
   mas similares mediante similitud coseno.

Ejemplos de uso:
    python conectarMongo.py --ingest
    python conectarMongo.py --ingest --skip-db
    python conectarMongo.py --query "Mensaje presidencial sobre educacion publica"
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import List, Sequence

import numpy as np
from pymongo import MongoClient, UpdateOne
from pymongo.collection import Collection
from pymongo.errors import PyMongoError
from sentence_transformers import SentenceTransformer

CADENA_CONEXION = (
    "mongodb://mongo1:30001,mongo2:30002,mongo3:30003/"
    "?replicaSet=my-replica-set&readPreference=primary&appname=MongoDB%20Compass&ssl=false"
)
MODELO_POR_DEFECTO = "sentence-transformers/all-MiniLM-L6-v2"
BASE_DATOS = "Politica"
COLECCION = "Discursos"
DIRECTORIO_DATOS = Path("DiscursosOriginales")
ARCHIVO_EXPORTACION = Path("discursos-final-202373011-4-202304074-6.json")


def crear_cliente(uri: str) -> MongoClient:
    """Crea un cliente de Mongo configurado para detectar fallas rapidamente."""
    return MongoClient(uri, serverSelectionTimeoutMS=5000)


def leer_archivo_texto(ruta: Path) -> str:
    try:
        return ruta.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return ruta.read_text(encoding="latin-1")


def documentos_desde_directorio(directorio: Path) -> List[dict]:
    if not directorio.exists():
        raise FileNotFoundError(f"No se encontro el directorio {directorio}")

    documentos: List[dict] = []
    for ruta_txt in sorted(directorio.glob("*.txt")):
        texto = leer_archivo_texto(ruta_txt).strip()
        if not texto:
            continue
        hash_sha = hashlib.sha256(texto.encode("utf-8")).hexdigest()
        documentos.append(
            {
                "_id": hash_sha,
                "texto": texto,
                "metadata": {
                    "filename": ruta_txt.name,
                    "source_path": str(ruta_txt),
                },
            }
        )
    return documentos


def codificar_textos(
    nombre_modelo: str, textos: Sequence[str], tamano_lote: int = 16
) -> np.ndarray:
    modelo = SentenceTransformer(nombre_modelo)
    embeddings = modelo.encode(
        list(textos),
        batch_size=tamano_lote,
        convert_to_numpy=True,
        normalize_embeddings=True,
        show_progress_bar=True,
    )
    return embeddings


def actualizar_documentos(coleccion: Collection, documentos: Sequence[dict]) -> None:
    operaciones = [
        UpdateOne({"_id": documento["_id"]}, {"$set": documento}, upsert=True)
        for documento in documentos
    ]
    if operaciones:
        resultado = coleccion.bulk_write(operaciones, ordered=False)
        print(
            f"Insertados: {resultado.upserted_count}, modificados: "
            f"{resultado.modified_count}"
        )


def exportar_json(documentos: Sequence[dict], ruta_salida: Path) -> None:
    ruta_salida.parent.mkdir(parents=True, exist_ok=True)
    with ruta_salida.open("w", encoding="utf-8") as archivo:
        json.dump(documentos, archivo, ensure_ascii=False, indent=2)
    print(f"Archivo JSON generado en {ruta_salida}")


def ejecutar_ingesta(
    cadena_conexion: str,
    directorio_dataset: Path,
    nombre_modelo: str,
    base_datos: str,
    nombre_coleccion: str,
    ruta_exportacion: Path | None,
    omitir_bd: bool,
    tamano_lote: int,
) -> None:
    documentos = documentos_desde_directorio(directorio_dataset)
    if not documentos:
        print("No se encontraron discursos para procesar.")
        return

    embeddings = codificar_textos(
        nombre_modelo, [documento["texto"] for documento in documentos], tamano_lote
    )
    for documento, embedding in zip(documentos, embeddings):
        documento["embedding"] = embedding.astype(float).tolist()
        documento["metadata"]["embedding_model"] = nombre_modelo

    if not omitir_bd:
        try:
            cliente = crear_cliente(cadena_conexion)
            base = cliente[base_datos]
            coleccion = base[nombre_coleccion]
            actualizar_documentos(coleccion, documentos)
            primario = cliente.admin.command("hello").get("primary")
            print(f"Replica set operativo. Primario actual: {primario}")
        except PyMongoError as error:
            print(
                "No fue posible insertar los documentos en MongoDB. "
                "Verifique que el cluster este arriba."
            )
            print(error)

    if ruta_exportacion:
        exportar_json(documentos, ruta_exportacion)


def similitud_coseno(matriz: np.ndarray, vector: np.ndarray) -> np.ndarray:
    vector_norm = vector / np.linalg.norm(vector)
    return np.dot(matriz, vector_norm)


def consulta_semantica(
    cadena_conexion: str,
    base_datos: str,
    nombre_coleccion: str,
    nombre_modelo: str,
    texto_consulta: str,
    top_k: int,
    tamano_lote: int,
) -> None:
    cliente = crear_cliente(cadena_conexion)
    coleccion = cliente[base_datos][nombre_coleccion]
    documentos = list(
        coleccion.find({}, {"_id": 1, "texto": 1, "embedding": 1, "metadata": 1})
    )
    if not documentos:
        print("La coleccion esta vacia. Ejecute primero el proceso de ingestion.")
        return

    modelo = SentenceTransformer(nombre_modelo)
    embedding_consulta = modelo.encode(
        [texto_consulta],
        batch_size=tamano_lote,
        convert_to_numpy=True,
        normalize_embeddings=True,
    )[0]

    matriz = np.array([documento["embedding"] for documento in documentos], dtype=np.float32)
    puntajes = similitud_coseno(matriz, embedding_consulta)

    ordenados = sorted(
        zip(documentos, puntajes), key=lambda par: par[1], reverse=True
    )[:top_k]

    print(f"\nTop {top_k} resultados para la consulta: \"{texto_consulta}\"\n")
    for posicion, (documento, puntaje) in enumerate(ordenados, start=1):
        metadatos = documento.get("metadata", {})
        nombre_archivo = metadatos.get("filename", "N/A")
        print(f"[{posicion}] ID: {documento['_id']} | archivo: {nombre_archivo}")
        print(f"   Puntaje coseno: {puntaje:.4f}")
        fragmento = documento["texto"][:220].replace("\n", " ")
        print(f"   Fragmento: {fragmento}...")
        print("-" * 80)


def parsear_argumentos() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Ingesta de discursos y busquedas semanticas usando MongoDB Replica Set."
    )
    parser.add_argument("--connection-string", default=CADENA_CONEXION)
    parser.add_argument("--database", default=BASE_DATOS)
    parser.add_argument("--collection", default=COLECCION)
    parser.add_argument("--dataset-dir", type=Path, default=DIRECTORIO_DATOS)
    parser.add_argument("--model-name", default=MODELO_POR_DEFECTO)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument(
        "--export-json",
        type=Path,
        default=ARCHIVO_EXPORTACION,
        help="Ruta del archivo JSON a generar tras la ingesta.",
    )
    parser.add_argument("--skip-db", action="store_true", help="Evita conectarse a MongoDB.")
    parser.add_argument("--ingest", action="store_true", help="Ejecuta el pipeline de ingesta.")
    parser.add_argument("--query", type=str, help="Texto a consultar de manera semantica.")
    parser.add_argument("--top-k", type=int, default=5, help="Numero de resultados a mostrar.")
    return parser.parse_args()


def main() -> None:
    argumentos = parsear_argumentos()

    if not argumentos.ingest and not argumentos.query:
        print("Debes indicar --ingest, --query o ambos.")
        return

    if argumentos.ingest:
        ejecutar_ingesta(
            cadena_conexion=argumentos.connection_string,
            directorio_dataset=argumentos.dataset_dir,
            nombre_modelo=argumentos.model_name,
            base_datos=argumentos.database,
            nombre_coleccion=argumentos.collection,
            ruta_exportacion=argumentos.export_json,
            omitir_bd=argumentos.skip_db,
            tamano_lote=argumentos.batch_size,
        )

    if argumentos.query:
        consulta_semantica(
            cadena_conexion=argumentos.connection_string,
            base_datos=argumentos.database,
            nombre_coleccion=argumentos.collection,
            nombre_modelo=argumentos.model_name,
            texto_consulta=argumentos.query,
            top_k=argumentos.top_k,
            tamano_lote=argumentos.batch_size,
        )


if __name__ == "__main__":
    main()
