"""
Funciones principales:
1. --ingest: Calcula los embeddings del corpus DiscursosOriginales y los inserta en la
   colección Politica.Discursos.
2. --query: Recibe una consulta textual, calcula su embedding y entrega los 5 documentos
   más similares mediante similitud coseno.

Ejemplos de uso:
    python conectarMongo.py --ingest
    python conectarMongo.py --ingest --skip-db --export-json tmp/discursos.json
    python conectarMongo.py --query "Mensaje presidencial sobre educación pública"
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

DEFAULT_CONNECTION = (
    "mongodb://mongo1:30001,mongo2:30002,mongo3:30003/"
    "?replicaSet=my-replica-set&readPreference=primary&appname=MongoDB%20Compass&ssl=false"
)
DEFAULT_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
DEFAULT_DB = "Politica"
DEFAULT_COLLECTION = "Discursos"
DEFAULT_DATASET = Path("DiscursosOriginales")
DEFAULT_EXPORT = Path("discursos-final-202373011-4-202304074-6.json")


def build_client(uri: str) -> MongoClient:
    """Crea un cliente de Mongo configurado para detectar fallas rápidamente."""
    return MongoClient(uri, serverSelectionTimeoutMS=5000)


def read_text_file(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return path.read_text(encoding="latin-1")


def documents_from_disk(dataset_dir: Path) -> List[dict]:
    if not dataset_dir.exists():
        raise FileNotFoundError(f"No se encontró el directorio {dataset_dir}")

    docs: List[dict] = []
    for txt_path in sorted(dataset_dir.glob("*.txt")):
        text = read_text_file(txt_path).strip()
        if not text:
            continue
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        docs.append(
            {
                "_id": digest,
                "texto": text,
                "metadata": {
                    "filename": txt_path.name,
                    "source_path": str(txt_path),
                },
            }
        )
    return docs


def encode_texts(
    model_name: str, texts: Sequence[str], batch_size: int = 16
) -> np.ndarray:
    model = SentenceTransformer(model_name)
    embeddings = model.encode(
        list(texts),
        batch_size=batch_size,
        convert_to_numpy=True,
        normalize_embeddings=True,
        show_progress_bar=True,
    )
    return embeddings


def upsert_documents(collection: Collection, docs: Sequence[dict]) -> None:
    operations = [
        UpdateOne({"_id": doc["_id"]}, {"$set": doc}, upsert=True) for doc in docs
    ]
    if operations:
        result = collection.bulk_write(operations, ordered=False)
        print(
            f"Insertados: {result.upserted_count}, modificados: "
            f"{result.modified_count}"
        )


def export_as_json(docs: Sequence[dict], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as handler:
        json.dump(docs, handler, ensure_ascii=False, indent=2)
    print(f"Archivo JSON generado en {output_path}")


def ingest_pipeline(
    connection: str,
    dataset_dir: Path,
    model_name: str,
    database: str,
    collection_name: str,
    export_path: Path | None,
    skip_db: bool,
    batch_size: int,
) -> None:
    docs = documents_from_disk(dataset_dir)
    if not docs:
        print("No se encontraron discursos para procesar.")
        return

    embeddings = encode_texts(model_name, [doc["texto"] for doc in docs], batch_size)
    for doc, embedding in zip(docs, embeddings):
        doc["embedding"] = embedding.astype(float).tolist()
        doc["metadata"]["embedding_model"] = model_name

    if not skip_db:
        try:
            client = build_client(connection)
            db = client[database]
            collection = db[collection_name]
            upsert_documents(collection, docs)
            primary = client.admin.command("hello").get("primary")
            print(f"Replica set operativo. Primario actual: {primary}")
        except PyMongoError as error:
            print(
                "No fue posible insertar los documentos en MongoDB. "
                "Verifique que el cluster esté arriba."
            )
            print(error)

    if export_path:
        export_as_json(docs, export_path)


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    b_norm = b / np.linalg.norm(b)
    return np.dot(a, b_norm)


def semantic_query(
    connection: str,
    database: str,
    collection_name: str,
    model_name: str,
    query_text: str,
    top_k: int,
    batch_size: int,
) -> None:
    client = build_client(connection)
    collection = client[database][collection_name]
    stored_docs = list(
        collection.find({}, {"_id": 1, "texto": 1, "embedding": 1, "metadata": 1})
    )
    if not stored_docs:
        print("La colección está vacía. Ejecute primero el proceso de ingestión.")
        return

    model = SentenceTransformer(model_name)
    query_embedding = model.encode(
        [query_text],
        batch_size=batch_size,
        convert_to_numpy=True,
        normalize_embeddings=True,
    )[0]

    matrix = np.array([doc["embedding"] for doc in stored_docs], dtype=np.float32)
    scores = cosine_similarity(matrix, query_embedding)

    ordered = sorted(
        zip(stored_docs, scores), key=lambda item: item[1], reverse=True
    )[:top_k]

    print(f"\nTop {top_k} resultados para la consulta: \"{query_text}\"\n")
    for position, (doc, score) in enumerate(ordered, start=1):
        metadata = doc.get("metadata", {})
        filename = metadata.get("filename", "N/A")
        print(f"[{position}] ID: {doc['_id']} | archivo: {filename}")
        print(f"   Puntaje coseno: {score:.4f}")
        snippet = doc["texto"][:220].replace("\n", " ")
        print(f"   Fragmento: {snippet}...")
        print("-" * 80)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Ingesta de discursos y búsquedas semánticas usando MongoDB Replica Set."
    )
    parser.add_argument("--connection-string", default=DEFAULT_CONNECTION)
    parser.add_argument("--database", default=DEFAULT_DB)
    parser.add_argument("--collection", default=DEFAULT_COLLECTION)
    parser.add_argument("--dataset-dir", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--model-name", default=DEFAULT_MODEL)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument(
        "--export-json",
        type=Path,
        default=DEFAULT_EXPORT,
        help="Ruta del archivo JSON a generar tras la ingesta.",
    )
    parser.add_argument("--skip-db", action="store_true", help="Evita conectarse a MongoDB.")
    parser.add_argument("--ingest", action="store_true", help="Ejecuta el pipeline de ingesta.")
    parser.add_argument("--query", type=str, help="Texto a consultar de manera semántica.")
    parser.add_argument("--top-k", type=int, default=5, help="Número de resultados a mostrar.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if not args.ingest and not args.query:
        print("Debes indicar --ingest, --query o ambos.")
        return

    if args.ingest:
        ingest_pipeline(
            connection=args.connection_string,
            dataset_dir=args.dataset_dir,
            model_name=args.model_name,
            database=args.database,
            collection_name=args.collection,
            export_path=args.export_json,
            skip_db=args.skip_db,
            batch_size=args.batch_size,
        )

    if args.query:
        semantic_query(
            connection=args.connection_string,
            database=args.database,
            collection_name=args.collection,
            model_name=args.model_name,
            query_text=args.query,
            top_k=args.top_k,
            batch_size=args.batch_size,
        )


if __name__ == "__main__":
    main()
