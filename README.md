## Tarea 3 Â· MongoDB Replica Set + BÃºsqueda SemÃ¡ntica

Este repositorio contiene todo lo solicitado en la Tarea 3 de INF-239:

- `deploy-202373011-4-202304074-6.yml` y `docker-compose.yml` describen el Replica Set de 3 nodos (1 primario + 2 secundarios) con `mongod --replSet my-replicaset`, keyfile y volumenes persistentes.
- `docker/init/init-rs.js` inicializa el Replica Set automÃ¡ticamente mediante el servicio auxiliar `rs-init`.
- `conectarMongo.py` automatiza el procesamiento del corpus `DiscursosOriginales` y las consultas semÃ¡nticas sobre la colecciÃ³n `Politica.Discursos`.
- `discursos-final-rol1-rol2.json` es el respaldo exportado con todos los documentos ya vectorizados.
- `pymongo-ROL1-ROL2.ipynb` reÃºne las evidencias pedidas (despliegue, ingesta, consultas y guÃ­a de robustez).

### Requisitos previos

1. **Docker Desktop** encendido (la conexiÃ³n da error si el servicio `com.docker.service` estÃ¡ detenido).
2. **Python 3.10+** con `pip`. Ejecuta:

   ```powershell
   python -m venv .venv
   .\.venv\Scripts\activate
   python -m pip install -r requirements.txt
   ```

3. **Hosts locales**: agrega estas entradas para que PyMongo resuelva los nombres del Replica Set.

   ```
   127.0.0.1   mongo1
   127.0.0.1   mongo2
   127.0.0.1   mongo3
   ```

4. (Opcional) Activa *Developer Mode* en Windows para que HuggingFace pueda crear symlinks en el cachÃ©.

### Puesta en marcha del Replica Set

```powershell
docker compose -f deploy-202373011-4-202304074-6.yml up -d
# o durante el desarrollo
docker compose up -d
```

El servicio `rs-init` ejecuta `docker/init/init-rs.js` y deja el Replica Set listo. Revisa el estado con:

```powershell
docker exec -it mongo1 mongosh --port 30001 --eval "rs.status()"
```

Para apagar la infraestructura:

```powershell
docker compose -f deploy-202373011-4-202304074-6.yml down
```

### Pipeline de ingesta + export

1. Procesa el corpus y sube los documentos (usa `--skip-db` si solo quieres generar el JSON):

   ```powershell
   python conectarMongo.py --ingest            # inserta en Politica.Discursos
   python conectarMongo.py --ingest --skip-db  # solo genera el JSON
   ```

2. El script calcula el hash SHA-256 del texto, genera embeddings con `sentence-transformers/all-MiniLM-L6-v2`, normaliza los vectores y los almacena asÃ­:

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

3. Los mismos documentos quedan guardados en `discursos-final-rol1-rol2.json` para el entregable 3.

### Consultas semÃ¡nticas

Ejecuta:

```powershell
python conectarMongo.py --query "Mensaje presidencial sobre educaciÃ³n pÃºblica"
```

El script:

1. Obtiene el embedding de la consulta.
2. Recupera los embeddings almacenados en MongoDB.
3. Calcula la similitud coseno y muestra el *top 5* con fragmentos, archivo original y puntaje.

### Evidencias y pruebas solicitadas

- Abre `pymongo-ROL1-ROL2.ipynb` (ya ejecutado) para revisar:
  - Comandos de despliegue (con mensajes cuando Docker no estÃ¡ activo).
  - EjecuciÃ³n del pipeline de ingesta y vista previa de los documentos en el JSON final.
  - Consulta semÃ¡ntica offline para documentar los resultados.
  - GuÃ­a para validar consistencia y alta disponibilidad (pasos de `docker stop/start` y `rs.status()`).
- En la defensa puedes repetir las celdas que usan `run_cmd` para capturar las salidas en vivo.

### Robustez (secciÃ³n 4 del enunciado)

1. **Consistencia**: Inserta/actualiza documentos con `python conectarMongo.py --ingest` y verifica en cada nodo:
   ```powershell
   docker exec -it mongo2 mongosh --port 30002 --eval "db.getSiblingDB('Politica').Discursos.countDocuments()"
   ```
   El conteo debe coincidir con el primario (`mongo1`).

2. **Alta disponibilidad**:
   ```powershell
   docker stop mongo1
   docker exec -it mongo2 mongosh --port 30002 --eval "rs.status().members.map(m => ({name: m.name, stateStr: m.stateStr}))"
   docker start mongo1
   ```
   Documenta el cambio de rol PRIMARY en el notebook.

### Limpieza

```powershell
docker compose -f deploy-202373011-4-202304074-6.yml down -v
Remove-Item .venv -Recurse -Force  # opcional
```

Con esto quedan listos los 4 entregables exigidos (compose, notebook, JSON final y README + scripts Python).
