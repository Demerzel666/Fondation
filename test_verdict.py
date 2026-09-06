import chromadb
from sentence_transformers import SentenceTransformer

model = SentenceTransformer("intfloat/multilingual-e5-large", device="cpu")
client = chromadb.PersistentClient(path="/home/data/fondation-ia-dev/rag/chroma_db")
coll = client.get_collection("fondation_knowledge")

questions = [
    "combien vaut le travail domestique non rémunéré des femmes, en milliards de dollars ?",
    "comment réaliser le bonheur de l'humanité ?",
]
for q in questions:
    print(f"\n❓ {q}")
    emb = model.encode(["query: " + q], normalize_embeddings=True)
    res = coll.query(query_embeddings=emb[0].tolist(), n_results=3,
                     include=["documents", "metadatas", "distances"])
    docs = res["documents"][0]
    for i in range(len(docs)):
        print(f"\n  --- Résultat {i+1} ---")
        print(docs[i][:400])
    print("\n  Métadonnées brutes (debug) :", res["metadatas"])
