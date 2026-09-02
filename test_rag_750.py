#!/usr/bin/env python3
"""
Test RAG — Évaluation de la qualité de récupération avec chunks 750 tokens.
Compare les scores, sources et pertinence sur des questions politiques clés.
"""

import sys
import os
import warnings

warnings.filterwarnings("ignore")

sys.path.insert(0, '/home/data/fondation-ia-dev')
from src.rag import search_context, format_context

# ============================================================================
# QUESTIONS TEST — Calibrées sur ta base politique
# ============================================================================

QUESTIONS = [
    {
        "q": "Qu'est-ce que le confédéralisme démocratique selon Ocalan ?",
        "expected_source": "ocalan"
    },
    {
        "q": "Comment Bookchin définit-il le municipalisme libertaire ?",
        "expected_source": "bookchin"
    },
    {
        "q": "Quelle est la critique de Fanon sur la violence coloniale ?",
        "expected_source": "fanon"
    },
    {
        "q": "Quelle est la pédagogie des opprimés selon Freire ?",
        "expected_source": "freire"
    },
    {
        "q": "Comment s'organise la révolution au Rojava ?",
        "expected_source": "rojava"
    },
    {
        "q": "Quelle est la relation entre capitalisme et reproduction sociale selon Federici ?",
        "expected_source": "federici"
    },
    {
        "q": "Quelle est la critique de l'industrialisation par l'écologie sociale ?",
        "expected_source": "bookchin"
    },
]

# ============================================================================
# EXÉCUTION DES TESTS
# ============================================================================

print("\n" + "=" * 70)
print("🧪 TEST RAG — CHUNKS 750 TOKENS")
print("=" * 70)
print(f"Questions: {len(QUESTIONS)}")
print(f"Modèle embeddings: intfloat/multilingual-e5-large")
print("=" * 70)

results_summary = []

for i, test in enumerate(QUESTIONS, 1):
    question = test["q"]
    expected = test["expected_source"]
    
    print(f"\n{'─' * 70}")
    print(f"❓ Question {i}/{len(QUESTIONS)}: {question}")
    print(f"🎯 Source attendue: {expected}")
    print(f"{'─' * 70}")
    
    results = search_context(question, top_k=3)
    
    if not results:
        print("   ❌ Aucun résultat retourné !")
        results_summary.append({
            "question": question,
            "expected": expected,
            "found": False,
            "avg_score": 0,
            "match": False
        })
        continue
    
    # Analyser les résultats
    scores = []
    sources_found = []
    match = False
    
    for j, r in enumerate(results, 1):
        score = r.get('score', 0)
        source = r.get('source', 'inconnu')
        text = r.get('text', '')
        scores.append(score)
        sources_found.append(source.lower())
        
        # Vérifier si la source attendue est dans les résultats
        if expected.lower() in source.lower():
            match = True
        
        # Afficher chaque résultat
        preview = text[:200].replace('\n', ' ')
        if len(text) > 200:
            preview += "..."
        
        print(f"   📄 Résultat {j}: score={score:.4f} | source={source[:60]}")
        print(f"      Texte: {preview}")
        print()
    
    avg_score = sum(scores) / len(scores)
    best_score = max(scores)
    
    status = "✅ MATCH" if match else "❌ MISS"
    
    print(f"   📊 Score moyen: {avg_score:.4f}")
    print(f"   📈 Meilleur score: {best_score:.4f}")
    print(f"   🎯 {status} — Source '{expected}' {'trouvée' if match else 'NON trouvée'}")
    
    results_summary.append({
        "question": question,
        "expected": expected,
        "found": True,
        "avg_score": avg_score,
        "best_score": best_score,
        "match": match,
        "sources": sources_found
    })

# ============================================================================
# RAPPORT FINAL
# ============================================================================

print("\n" + "=" * 70)
print("📊 RAPPORT FINAL")
print("=" * 70)

total = len(results_summary)
matches = sum(1 for r in results_summary if r["match"])
found = sum(1 for r in results_summary if r["found"])
avg_scores = [r["avg_score"] for r in results_summary if r["found"]]
best_scores = [r["best_score"] for r in results_summary if r["found"]]

print(f"\n   Questions testées:     {total}")
print(f"   Résultats obtenus:    {found}/{total}")
print(f"   Sources matching:     {matches}/{total} ({matches/total*100:.0f}%)")

if avg_scores:
    global_avg = sum(avg_scores) / len(avg_scores)
    global_best = sum(best_scores) / len(best_scores)
    print(f"   Score moyen global:   {global_avg:.4f}")
    print(f"   Meilleur score moy:  {global_best:.4f}")

print(f"\n   Détail par question:")
print(f"   {'Question':<50} {'Attendu':<12} {'Match':<6} {'Score':<8}")
print(f"   {'-'*50} {'-'*12} {'-'*6} {'-'*8}")

for r in results_summary:
    q_short = r["question"][:48]
    exp = r["expected"][:10]
    match_str = "✅" if r["match"] else "❌"
    score_str = f"{r['avg_score']:.4f}" if r["found"] else "N/A"
    print(f"   {q_short:<50} {exp:<12} {match_str:<6} {score_str:<8}")

# ============================================================================
# ÉVALUATION QUALITATIVE
# ============================================================================

print(f"\n{'─' * 70}")
print("📝 ÉVALUATION QUALITATIVE")
print(f"{'─' * 70}")

if avg_scores:
    global_avg = sum(avg_scores) / len(avg_scores)
    
    if global_avg >= 0.8:
        print("   🟢 Excellente pertinence — chunks 750 tokens performants")
    elif global_avg >= 0.6:
        print("   🟡 Pertinence correcte — envisager ajustements")
    elif global_avg >= 0.4:
        print("   🟠 Pertinence faible — revoir le chunking ou les embeddings")
    else:
        print("   🔴 Pertinence insuffisante — problème de configuration RAG")

if matches < total / 2:
    print("   ⚠️  Moins de 50% des sources attendues retrouvées")
    print("   → Considérer augmenter top_k ou revoir la qualité des textes")
elif matches == total:
    print("   🎉 Toutes les sources attendues ont été retrouvées !")

print(f"\n{'=' * 70}")
print("✅ Test terminé")
print(f"{'=' * 70}\n")
