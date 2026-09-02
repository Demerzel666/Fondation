# Déclaration de la fonction
def afficher_bienvenue(nom):
    """
    Cette fonction affiche un message de bienvenue personnalisé.

    Paramètres:
    nom (str): Le nom de la personne à saluer

    Retour:
    None
    """
    message = f"Bienvenue, {nom} !"
    print(message)

# Exemple d'utilisation
if __name__ == "__main__":
    nom_utilisateur = "Alice"
    afficher_bienvenue(nom_utilisateur)
