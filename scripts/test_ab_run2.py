#!/usr/bin/env python
# =============================================================================
# Test A/B — Run 2 fine-tuning
# Candidat : port 8083 (fondation-ft2.Q4_K_M) | Baseline : port 8080 (prod)
# Pour chaque question : appelle les DEUX serveurs, enregistre tout.
# =============================================================================
import json, os, sys, urllib.request, datetime

# --- Config ---
PORT_CANDIDAT = "8083"
PORT_BASELINE = "8080"      # met à None si la prod n'est pas lancée
DATASET = "dataset/fondation_v1_with_rag.jsonl"
SYSTEM_PROMPT_FILE = "prompts/politique.txt"
OUTDIR = os.path.join("test_results",
                      datetime.datetime.now().strftime("run2-%Y%m%d-%H%M"))
MAX_TOKENS = 1200

QUESTIONS_REPLAY = [
    # (label, filtre sur le texte de la question du dataset)
    ("q1-etat",        "l'État"),
    ("q2-qui-es-tu",   "qui es"),
    ("q3-luxemburg",   "uxembur"),
]

QUESTIONS_LIVE = [
    # (label, question posée telle quelle, avec system prompt mais SANS RAG)
    ("q4-hors-dataset", "Explique-moi simplement comment fonctionnent les expressions régulières."),
    ("q5-tes-qui",      "T'es qui ?"),
]

def call_llm(port, messages, temperature=0.7):
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}/v1/chat/completions",
        data=json.dumps({"messages": messages,
                         "max_tokens": MAX_TOKENS,
                         "temperature": temperature}).encode(),
        headers={"Content-Type": "application/json"})
    r = json.load(urllib.request.urlopen(req, timeout=300))
    m = r["choices"][0]["message"]
    content = m.get("content") or "(VIDE)"
    reason = m.get("reasoning_content") or ""
    return content, reason, r["usage"]

def save(label, port_name, content, reason):
    path = os.path.join(OUTDIR, f"{label}-{port_name}.txt")
    with open(path, "w") as f:
        f.write("=== CONTENT ===\n" + content + "\n")
        if reason:
            f.write("\n=== RAISONNEMENT ===\n" + reason + "\n")
    print(f"  [SAUVÉ] {path}")

def main():
    os.makedirs(OUTDIR, exist_ok=True)

    with open(SYSTEM_PROMPT_FILE) as f:
        system_prompt = f.read().strip()

    exemples = []
    with open(DATASET) as f:
        for line in f:
            exemples.append(json.loads(line))

    # --- Partie 1 : replay exact (conditions d'entraînement) ---
    for label, filtre in QUESTIONS_REPLAY:
        ex = None
        for e in exemples:
            msgs = e["messages"]
            if len(msgs) >= 3 and filtre.lower() in msgs[1]["content"].lower():
                ex = e
                break
        if ex is None:
            print(f"[SKIP] {label} : aucun exemple trouvé pour '{filtre}'")
            continue
        entree = ex["messages"][:-1]   # tout sauf la réponse
        attendu = ex["messages"][-1]["content"]
        with open(os.path.join(OUTDIR, f"{label}-attendu.txt"), "w") as f:
            f.write(attendu)
        print(f"\n[{label}] (replay — RAG de l'entraînement)")
        for port, nom in [(PORT_CANDIDAT, "candidat-8083"), (PORT_BASELINE, "baseline-8080")]:
            if port is None:
                continue
            c, r, u = call_llm(port, entree)
            save(label, nom, c, r)
            print(f"    {nom} : {len(c)} caractères")

    # --- Partie 2 : live (system prompt, sans RAG — comme prod hors-sujet) ---
    for label, question in QUESTIONS_LIVE:
        messages = [{"role": "system", "content": system_prompt},
                    {"role": "user", "content": question}]
        print(f"\n[{label}] (live — {question[:50]})")
        for port, nom in [(PORT_CANDIDAT, "candidat-8083"), (PORT_BASELINE, "baseline-8080")]:
            if port is None:
                continue
            c, r, u = call_llm(port, messages)
            save(label, nom, c, r)
            print(f"    {nom} : {len(c)} caractères")

    print(f"\n[DONE] Tous les résultats dans {OUTDIR}/")
    print("Lecture conseillée : candidat vs baseline côte à côte, et -attendu pour les replay.")

if __name__ == "__main__":
    sys.exit(main())
