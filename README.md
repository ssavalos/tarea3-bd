## Tarea 3 INF-239

Grupo 5:
- Sofia Avalos: 202373011-4
- Nestor Lopez: 202304074-6

Esta tarea incluye exactamente los cuatro entregables solicitados:

1. `deploy-202373011-4-202304074-6.yml`: Replica Set de 3 nodos con keyfile y volumenes persistentes.
2. `pymongo-202373011-4-202304074-6.ipynb`: notebook ejecutado con las evidencias (despliegue, ingesta, consultas y pruebas de robustez).
3. `discursos-final-202373011-4-202304074-6.json`: respaldo exportado con todos los documentos ya vectorizados.
4. `README.md`: instrucciones de uso, supuestos y pasos reproducibles de la tarea.

### Requisitos previos

1. **Docker Desktop** encendido (el comando falla si el servicio `com.docker.service` esta detenido).
2. **Python 3.10+ con pip**. Instalacion sugerida:

   ```powershell
   python -m venv .venv
   .\.venv\Scripts\activate
   python -m pip install -r requirements.txt
   ```

3. **Hosts locales**: agrega las entradas para que PyMongo resuelva los nombres del Replica Set.

   ```
   127.0.0.1   mongo1
   127.0.0.1   mongo2
   127.0.0.1   mongo3
   ```

4. (Opcional) Activa Developer Mode en Windows para que HuggingFace pueda crear symlinks en el cache.

### Puesta en marcha del Replica Set

```powershell
docker compose -f deploy-202373011-4-202304074-6.yml up -d
```

Para apagar la infraestructura:

```powershell
docker compose -f deploy-202373011-4-202304074-6.yml down
```

### Pipeline de ingesta y export

1. Procesa el corpus y sube los documentos (usa `--skip-db` si solo quieres generar el JSON):

   ```powershell
   python conectarMongo.py --ingest            # inserta en Politica.Discursos
   python conectarMongo.py --ingest --skip-db  # solo genera el JSON
   ```

2. El script calcula el hash SHA-256 del texto, genera embeddings con `sentence-transformers/all-MiniLM-L6-v2`, normaliza los vectores y los almacena asi:

   ```json
   {
     "_id": "<sha256>",
     "texto": "<contenido completo>",
     "embedding": [0.0147, -0.2195, ...],
     "metadata": {
       "filename": "100020.txt",
       "source_path": "DiscursosOriginales/100020.txt",
       "embedding_model": "sentence-transformers/all-MiniLM-L6-v2"
     }
   }
   ```

3. Los mismos documentos quedan guardados en `discursos-final-202373011-4-202304074-6.json` para el entregable 3.

### Consultas semanticas

```powershell
python conectarMongo.py --query "Mensaje presidencial sobre educacion publica"
```

El script obtiene el embedding de la consulta, calcula la similitud coseno con los embeddings almacenados y muestra el top 5 con fragmentos, archivo original y puntaje.

### Evidencias y pruebas solicitadas

Abre `pymongo-202373011-4-202304074-6.ipynb` (ya ejecutado) para revisar:

- Comandos de despliegue (incluye mensajes cuando Docker no esta activo).
- Ejecucion del pipeline de ingesta y vista previa de los documentos en el JSON final.
- Consulta semantica offline para documentar los resultados.
- Guia para validar consistencia y alta disponibilidad.

### Robustez

1. **Consistencia**: inserta o actualiza documentos con `python conectarMongo.py --ingest` y verifica en cada nodo:

   ```powershell
   docker exec -it mongo2 mongosh --port 30002 --eval "db.getSiblingDB('Politica').Discursos.countDocuments()"
   ```

2. **Alta disponibilidad**:

   ```powershell
   docker stop mongo1
   docker exec -it mongo2 mongosh --port 30002 --eval "rs.status().members.map(m => ({name: m.name, stateStr: m.stateStr}))"
   docker start mongo1
   ```

### Limpieza

```powershell
docker compose -f deploy-202373011-4-202304074-6.yml down -v
Remove-Item .venv -Recurse -Force  # opcional
```
