from flask import Flask, render_template, request, redirect, url_for, jsonify, flash
from flask_sqlalchemy import SQLAlchemy
import random
import json
from datetime import datetime
from flask import Response

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///mythic_gme.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = 'cle_secrete_mythic'

db = SQLAlchemy(app)

# Modèles de base de données
class GameState(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    chaos_factor = db.Column(db.Integer, default=5)

class FateQuestion(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    question = db.Column(db.String(500), nullable=False)
    odds = db.Column(db.String(50), nullable=False)
    answer = db.Column(db.String(50), nullable=False)
    base_chance = db.Column(db.Integer, nullable=False)
    final_chance = db.Column(db.Integer, nullable=False)
    roll = db.Column(db.Integer, nullable=False)
    exc_yes_threshold = db.Column(db.Integer, nullable=False)
    exc_no_threshold = db.Column(db.Integer, nullable=False)
    random_event = db.Column(db.Boolean, default=False)

class Objective(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    description = db.Column(db.String(500), nullable=False)

class NPC(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.String(500), nullable=True)

class Scene(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.String(1000), nullable=True)
    status = db.Column(db.String(50), default="normale")  # normale, altérée, interrompue

class CustomTable(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    # Les valeurs seront stockées en texte brut, séparées par des sauts de ligne
    values = db.Column(db.Text, nullable=False)

class JournalEntry(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.DateTime, default=datetime.utcnow)  # Date automatique
    content = db.Column(db.Text, nullable=False)

class Inventory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)

class InventoryItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    inventory_id = db.Column(db.Integer, db.ForeignKey('inventory.id'), nullable=False)
    name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=True)
    quantity = db.Column(db.Integer, default=1)
    inventory = db.relationship('Inventory', backref=db.backref('items', lazy=True, cascade="all, delete"))

class PlayerCharacter(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)  # Nom du personnage
    description = db.Column(db.Text, nullable=True)   # Petite description ou historique

class PlayerAttribute(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    character_id = db.Column(db.Integer, db.ForeignKey('player_character.id'), nullable=False)
    attribute_name = db.Column(db.String(200), nullable=False)
    attribute_value = db.Column(db.String(200), nullable=False)
    is_numeric = db.Column(db.Boolean, default=False)  # Nouveau champ pour indiquer si c'est numérique
    character = db.relationship('PlayerCharacter', backref=db.backref('attributes', lazy=True, cascade="all, delete"))

class DiceRollHistory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    faces = db.Column(db.Integer, nullable=False)
    roll = db.Column(db.Integer, nullable=False)
    date = db.Column(db.DateTime, default=datetime.utcnow)


with app.app_context():
    db.create_all()

# Fonction Fate Check selon la règle du PDF pour l'événement aléatoire
def fate_check(odds, chaos_factor):
    table_odds = {
        "Certain": 90,
        "Presque Certain": 85,
        "Très Probable": 75,
        "Probable": 65,
        "50/50": 50,
        "Improbable": 35,
        "Très Improbable": 25,
        "Presque Impossible": 15,
        "Impossible": 10
    }
    
    base_chance = table_odds.get(odds, 50)
    modifier = (chaos_factor - 5) * 5
    final_chance = min(max(base_chance + modifier, 1), 99)
    
    exc_yes_threshold = int(final_chance * 0.2)
    exc_no_threshold = 100 - int((100 - final_chance) * 0.2)
    
    roll = random.randint(1, 100)
    roll_str = str(roll)
    # Un Random Event est déclenché si le résultat est un double (11, 22, 33, etc.)
    # dont le chiffre (ex : 5 pour 55) est inférieur ou égal au Facteur de Chaos.
    is_double = (len(roll_str) == 2 and roll_str[0] == roll_str[1] and int(roll_str[0]) <= chaos_factor)
    
    if roll <= exc_yes_threshold:
        answer = "Oui Exceptionnel"
    elif roll <= final_chance:
        answer = "Oui"
    elif roll >= exc_no_threshold:
        answer = "Non Exceptionnel"
    else:
        answer = "Non"
    
    return {
        "answer": answer,
        "base_chance": base_chance,
        "final_chance": final_chance,
        "roll": roll,
        "exc_yes_threshold": exc_yes_threshold,
        "exc_no_threshold": exc_no_threshold,
        "random_event": is_double
    }

@app.route("/")
def index():
    game_state = GameState.query.first()
    if not game_state:
        game_state = GameState(chaos_factor=5)
        db.session.add(game_state)
        db.session.commit()
        
    fate_page = request.args.get('fate_page', 1, type=int)
    fate_questions = FateQuestion.query.order_by(FateQuestion.id.desc()).paginate(page=fate_page, per_page=6, error_out=False)

    objectives = Objective.query.all()
    npcs = NPC.query.all()
    scenes = Scene.query.all()
    custom_tables = CustomTable.query.order_by(CustomTable.id.desc()).all()
    
    # Pagination pour le journal (5 entrées par page, page 1 par défaut)
    page = request.args.get('page', 1, type=int)
    journal_entries = JournalEntry.query.order_by(JournalEntry.date.desc()).paginate(page=page, per_page=5, error_out=False)
    
    last_fq = fate_questions.items[0] if fate_questions.items else None
    current_scene = Scene.query.order_by(Scene.id.desc()).first()

    inventories = Inventory.query.all()

    players = PlayerCharacter.query.all()

    return render_template("index.html", 
                       chaos_factor=game_state.chaos_factor, 
                       fate_questions=fate_questions, 
                       objectives=objectives, 
                       npcs=npcs, 
                       scenes=scenes, 
                       last_fq=last_fq, 
                       current_scene=current_scene, 
                       custom_tables=custom_tables, 
                       journal_entries=journal_entries,
                       current_fate_page=fate_page,
                       inventories=inventories,
                       players=players,
                       custom_tables_json=json.dumps([{ "id": t.id, "name": t.name, "values": t.values } for t in custom_tables]))


@app.route("/ask_fate", methods=["POST"])
def ask_fate():
    question = request.form.get("question")
    odds = request.form.get("odds")
    game_state = GameState.query.first()
    
    result = fate_check(odds, game_state.chaos_factor)
    
    new_question = FateQuestion(
        question=question,
        odds=odds,
        answer=result["answer"],
        base_chance=result["base_chance"],
        final_chance=result["final_chance"],
        roll=result["roll"],
        exc_yes_threshold=result["exc_yes_threshold"],
        exc_no_threshold=result["exc_no_threshold"],
        random_event=result["random_event"]
    )
    db.session.add(new_question)
    db.session.commit()
    return redirect(url_for("index") + "#fate")

@app.route("/delete_fate/<int:question_id>")
def delete_fate(question_id):
    fq = FateQuestion.query.get_or_404(question_id)
    db.session.delete(fq)
    db.session.commit()
    return redirect(url_for("index") + "#fate")

@app.route("/add_objective", methods=["POST"])
def add_objective():
    description = request.form.get("description")
    new_objective = Objective(description=description)
    db.session.add(new_objective)
    db.session.commit()
    return redirect(url_for("index") + "#objectives")

@app.route("/delete_objective/<int:objective_id>")
def delete_objective(objective_id):
    obj = Objective.query.get_or_404(objective_id)
    db.session.delete(obj)
    db.session.commit()
    return redirect(url_for("index") + "#objectives")

@app.route("/add_npc", methods=["POST"])
def add_npc():
    name = request.form.get("name")
    description = request.form.get("description")
    new_npc = NPC(name=name, description=description)
    db.session.add(new_npc)
    db.session.commit()
    return redirect(url_for("index") + "#npcs")

@app.route("/delete_npc/<int:npc_id>")
def delete_npc(npc_id):
    npc = NPC.query.get_or_404(npc_id)
    db.session.delete(npc)
    db.session.commit()
    return redirect(url_for("index") + "#npcs")

@app.route("/random_npc")
def random_npc():
    npcs = NPC.query.all()
    if npcs:
        npc = random.choice(npcs)
        return jsonify({"name": npc.name, "description": npc.description})
    else:
        return jsonify({"error": "Aucun PNJ enregistré."})

@app.route("/add_scene", methods=["POST"])
def add_scene():
    title = request.form.get("title")
    description = request.form.get("description")
    status = request.form.get("status", "normale")
    new_scene = Scene(title=title, description=description, status=status)
    db.session.add(new_scene)
    db.session.commit()
    return redirect(url_for("index") + "#scenes")

@app.route("/delete_scene/<int:scene_id>")
def delete_scene(scene_id):
    scene = Scene.query.get_or_404(scene_id)
    db.session.delete(scene)
    db.session.commit()
    return redirect(url_for("index") + "#scenes")

@app.route("/adjust_chaos", methods=["POST"])
def adjust_chaos():
    adjustment = int(request.form.get("adjustment"))
    game_state = GameState.query.first()
    game_state.chaos_factor = max(1, min(9, game_state.chaos_factor + adjustment))
    db.session.commit()
    return redirect(url_for("index") + "#fate")

# Endpoint pour le Chaos Roll des scènes sur d10
@app.route("/scene_chaos_roll")
def scene_chaos_roll():
    game_state = GameState.query.first()
    cf = game_state.chaos_factor
    roll = random.randint(1, 10)
    # Règle pour le Chaos Roll des scènes :
    # Si roll > cf → scène normale
    # Si roll ≤ cf et impair → scène altérée
    # Si roll ≤ cf et pair → scène interrompue
    if roll > cf:
        status = "normale"
    else:
        if roll % 2 == 1:
            status = "altérée"
        else:
            status = "interrompue"
    return jsonify({"roll": roll, "status": status})

# Lanceur de d100
@app.route("/roll_d100")
def roll_d100():
    roll = random.randint(1, 100)
    return jsonify({"roll": roll})

@app.route("/journal", defaults={'page': 1})
@app.route("/journal/page/<int:page>")
def journal(page):
    per_page = 5  # Nombre d'entrées par page
    journal_entries = JournalEntry.query.order_by(JournalEntry.date.desc()).paginate(page=page, per_page=per_page, error_out=False)
    fate_page = request.args.get('fate_page', 1, type=int)
    fate_questions = FateQuestion.query.order_by(FateQuestion.id.desc()).paginate(page=fate_page, per_page=6, error_out=False)
    print(journal_entries)
    return render_template("index.html", journal_entries=journal_entries, current_page=page)

@app.route("/add_journal_entry", methods=["POST"])
def add_journal_entry():
    content = request.form.get("content").strip()
    if content:
        new_entry = JournalEntry(content=content)
        db.session.add(new_entry)
        db.session.commit()
    return redirect(url_for("index") + "#journal")

@app.route("/delete_journal_entry/<int:entry_id>")
def delete_journal_entry(entry_id):
    entry = JournalEntry.query.get_or_404(entry_id)
    db.session.delete(entry)
    db.session.commit()
    return redirect(url_for("index") + "#journal")

@app.route("/export_journal")
def export_journal():
    entries = JournalEntry.query.order_by(JournalEntry.date.asc()).all()
    markdown_content = "# Journal\n\n"
    for entry in entries:
        markdown_content += f"## {entry.date.strftime('%Y-%m-%d %H:%M:%S')}\n\n{entry.content}\n\n---\n\n"
    
    return Response(markdown_content, mimetype="text/markdown", headers={"Content-Disposition": "attachment;filename=journal.md"})

@app.route("/add_inventory", methods=["POST"])
def add_inventory():
    title = request.form.get("title").strip()
    if title:
        new_inventory = Inventory(title=title)
        db.session.add(new_inventory)
        print(new_inventory)
        db.session.commit()
    return redirect(url_for("index") + "#inventories")

@app.route("/delete_inventory/<int:inventory_id>")
def delete_inventory(inventory_id):
    inventory = Inventory.query.get_or_404(inventory_id)
    db.session.delete(inventory)
    db.session.commit()
    return redirect(url_for("index") + "#inventories")

@app.route("/add_inventory_item/<int:inventory_id>", methods=["POST"])
def add_inventory_item(inventory_id):
    name = request.form.get("name")
    description = request.form.get("description")
    quantity = request.form.get("quantity", type=int)  # Récupérer la quantité en tant qu'entier

    if not name or quantity < 1:
        flash("Le nom de l'objet et une quantité valide sont requis.", "danger")
        return redirect(url_for("index"))

    new_item = InventoryItem(name=name, description=description, quantity=quantity, inventory_id=inventory_id)
    db.session.add(new_item)
    db.session.commit()
    flash("Objet ajouté avec succès à l'inventaire.", "success")
    return redirect(url_for("index"))

@app.route("/delete_inventory_item/<int:item_id>")
def delete_inventory_item(item_id):
    item = InventoryItem.query.get_or_404(item_id)
    db.session.delete(item)
    db.session.commit()
    return redirect(url_for("index") + "#inventories")

@app.route("/update_attribute/<int:attribute_id>/<string:operation>", methods=["POST"])
def update_attribute(attribute_id, operation):
    attr = PlayerAttribute.query.get_or_404(attribute_id)
    
    # Vérifier que l'attribut est numérique
    if attr.is_numeric:
        try:
            value = int(attr.attribute_value)
        except ValueError:
            value = 0  # Si la valeur n'est pas numérique, le réinitialiser
        if operation == "increase":
            value += 1
        elif operation == "decrease":
            value -= 1
        attr.attribute_value = str(value)
        db.session.commit()
        return jsonify({"success": True, "new_value": value})  # Retour JSON
    
    return jsonify({"success": False}), 400  # Erreur si l'attribut n'est pas numérique

@app.route("/update_item_quantity/<int:item_id>/<string:operation>", methods=["POST"])
def update_item_quantity(item_id, operation):
    item = InventoryItem.query.get_or_404(item_id)
    if operation == "increase":
        item.quantity += 1
    elif operation == "decrease" and item.quantity > 0:
        item.quantity -= 1
    db.session.commit()
    return jsonify({"success": True, "new_quantity": item.quantity, "inventory_id": item.inventory_id})


# -
# Tables aléatoires du PDF

# TABLE D'AJUSTEMENT DE SCÈNE (1d10)
SCENE_ADJUSTMENT_TABLE = {
    1: "Retirer un personnage",
    2: "Ajouter un personnage",
    3: "Réduire/Retirer une activité",
    4: "Augmenter une activité",
    5: "Retirer un objet",
    6: "Ajouter un objet",
    7: "Faire 2 ajustements",
    8: "Faire 2 ajustements",
    9: "Faire 2 ajustements",
    10: "Faire 2 ajustements"
}

# TABLE DE FOCUS D'ÉVÉNEMENT ALÉATOIRE (1d100)
def roll_random_event_focus():
    roll = random.randint(1, 100)
    if 1 <= roll <= 5:
        result = "Événement lointain: Votre PC attend des nouvelles de loin et le moment semble bien choisi pour le bon moment pour qu'elles arrivent."
    elif 6 <= roll <= 10:
        result = "Événement ambigu: L'aventure s'est ralentie et vous et vous êtes prêt pour un mystère à poursuivre."
    elif 11 <= roll <= 20:
        result = "Nouveau PNJ: Il y a une raison logique pour qu'un qu'un nouveau PNJ apparaisse dans votre dans votre aventure."
    elif 21 <= roll <= 40:
        result = "Action de PNJ: Votre PC attend l'action d'un action des PNJ pour faire avancer l'aventure."
    elif 41 <= roll <= 45:
        result = "PNJ négatif: Vous voulez déplacer le centre d'intérêt de votre aventure sur un PNJ en ce moment, peut-être pour développer de nouvelles nouvelles intrigues dans votre aventure."
    elif 46 <= roll <= 50:
        result = "PNJ positif: Vous voulez déplacer le centre d'intérêt de votre aventure sur un PNJ en ce moment, peut-être pour développer de nouvelles nouvelles intrigues dans votre aventure."
    elif 51 <= roll <= 55:
        result = "Avancer vers un fil narratif: Votre aventure est au point mort et a besoin d'un coup de pouce. Ceci est particulièrement utile pour une scène d'interruption."
    elif 56 <= roll <= 65:
        result = "S'éloigner d'un fil narratif: Vous voulez un nouveau défi pour votre PC."
    elif 66 <= roll <= 70:
        result = "Fermer un fil narratif: L'aventure s'est compliquée compliquée et vous voulez réduire la liste des fils de discussion."
    elif 71 <= roll <= 80:
        result = "Désavantage pour le PJ: Vous voulez un nouveau défi pour votre PC."
    elif 81 <= roll <= 85:
        result = "Avantage pour le PJ: Votre PC traverse une période difficile et a besoin d'une pause."
    elif 86 <= roll <= 100:
        result = "Contexte actuel: La table Evénement aléatoire peut aider à expliquer le résultat d'une question sur le destin, ou un événement aléatoire peut perturber l'action en cours"
    return roll, result

# TABLES DE SIGNIFICATION : ACTIONS, DESCRIPTEURS, ÉLÉMENTS ...
MEANING_ACTIONS = {
    1: "Abandonner", 2: "Accompagner", 3: "Activer", 4: "Accepter", 5: "Embûcher",
    6: "Arriver", 7: "Assister", 8: "Attaquer", 9: "Atteindre", 10: "Marchander",
    11: "Se lier d'amitié", 12: "Accorder", 13: "Trahir", 14: "Bloquer", 15: "Casser",
    16: "Porter", 17: "Célébrer", 18: "Changer", 19: "Fermer", 20: "Combiner",
    21: "Communiquer", 22: "Cacher", 23: "Continuer", 24: "Contrôler", 25: "Créer",
    26: "Tromper", 27: "Diminuer", 28: "Défendre", 29: "Retarder", 30: "Dénier",
    31: "Partir", 32: "Déposer", 33: "Détruire", 34: "Disputer", 35: "Perturber",
    36: "Se méfier", 37: "Diviser", 38: "Laisser tomber", 39: "Facile", 40: "Énergiser",
    41: "Échapper", 42: "Exposer", 43: "Échouer", 44: "Se battre", 45: "Fuir",
    46: "Libérer", 47: "Guider", 48: "Nuire", 49: "Guérir", 50: "Gêner",
    51: "Imiter", 52: "Emprisonner", 53: "Augmenter", 54: "Satisfaire", 55: "Informer",
    56: "S'informer", 57: "Inspecter", 58: "Envahir", 59: "Quitter", 60: "Attirer",
    61: "Abuser", 62: "Bouger", 63: "Négliger", 64: "Observer", 65: "Ouvrir",
    66: "S'opposer", 67: "Renverser", 68: "Louer", 69: "Procéder", 70: "Protéger",
    71: "Punir", 72: "Poursuivre", 73: "Recruter", 74: "Refuser", 75: "Libérer",
    76: "Abandonner", 77: "Réparer", 78: "Repousser", 79: "Retourner", 80: "Récompenser",
    81: "Ruinier", 82: "Séparer", 83: "Commencer", 84: "Arrêter", 85: "Étrange",
    86: "Lutter", 87: "Réussir", 88: "Soutenir", 89: "Réprimer", 90: "Prendre",
    91: "Menacer", 92: "Transformer", 93: "Piéger", 94: "Voyager", 95: "Triompher",
    96: "Trêve", 97: "Faire confiance", 98: "Utiliser", 99: "Usurper", 100: "Gaspiller",
    101: "Avantage", 102: "Adversité", 103: "Accord", 104: "Animal", 105: "Attention",
    106: "Équilibre", 107: "Bataille", 108: "Bénéfices", 109: "Bâtiment", 110: "Fardeau",
    111: "Bureaucratie", 112: "Affaires", 113: "Chaos", 114: "Confort", 115: "Achèvement",
    116: "Conflit", 117: "Coopération", 118: "Danger", 119: "Défense", 120: "Épuisement",
    121: "Désavantage", 122: "Distraction", 123: "", 124: "Émotion", 125: "Ennemi",
    126: "Énergie", 127: "Environnement", 128: "Attente", 129: "Extérieur", 130: "Extravagance",
    131: "Échec", 132: "Gloire", 133: "Peur", 134: "Liberté", 135: "Ami", 136: "Objectif",
    137: "Groupe", 138: "Santé", 139: "Obstruction", 140: "Maison", 141: "Espoir",
    142: "Idée", 143: "Maladie", 144: "Illusion", 145: "Individu", 146: "Information",
    147: "Innocent", 148: "Intellect", 149: "Intérieur", 150: "Investissement", 151: "Leadership",
    152: "Légal", 153: "Lieu", 154: "Militaire", 155: "Malchance", 156: "Mundain", 157: "Nature",
    158: "Besoins", 159: "Nouvelles", 160: "Normal", 161: "Objet", 162: "Obscurité", 163: "Officiel",
    164: "Opposition", 165: "Extérieur", 166: "Douleur", 167: "Chemin", 168: "Paix", 169: "Peuple",
    170: "Personnel", 171: "Physique", 172: "Intrigue", 173: "Portail", 174: "Biens", 175: "Pauvreté",
    176: "Pouvoir", 177: "Prison", 178: "Projet", 179: "Protection", 180: "Rassurance",
    181: "Représentant", 182: "Richesses", 183: "Sécurité", 184: "Force", 185: "Succès", 186: "Souffrance",
    187: "Surprise", 188: "Tactique", 189: "Technologie", 190: "Tension", 191: "Temps", 192: "Procès",
    193: "Valeur", 194: "Véhicule", 195: "Victoire", 196: "Vulnérabilité", 197: "Arme", 198: "Météo",
    199: "Travail", 200: "Blessure"
}

MEANING_DESCRIPTORS = {
    1: "Aventureusement", 2: "Agressivement", 3: "Anxieusement", 4: "Maladroitement", 5: "Magnifiquement",
    6: "Sombrement", 7: "Audacieusement", 8: "Courageusement", 9: "Activement", 10: "Calmement",
    11: "Soigneusement", 12: "Négligemment", 13: "Prudemment", 14: "Inlassablement", 15: "Joyeusement",
    16: "Combativement", 17: "Détachément", 18: "Fougueusement", 19: "Curieusement", 20: "Dangereusement",
    21: "Défiant", 22: "Délibérément", 23: "Délicatement", 24: "Délectablement", 25: "Sombrement",
    26: "Efficacement", 27: "Émotionnellement", 28: "Énergiquement", 29: "Énormément", 30: "Avec enthousiasme",
    31: "Excitément", 32: "Peur", 33: "Férocement", 34: "Avec force", 35: "Bêtement", 36: "Heureusement",
    37: "Frénétiquement", 38: "Librement", 39: "Effrayamment", 40: "Entièrement", 41: "Généreusement",
    42: "Doucement", 43: "Avec plaisir", 44: "Gracieusement", 45: "Reconnaissant", 46: "Heureux", 47: "Hâtivement",
    48: "Sainement", 49: "Avec aide", 50: "Sans aide", 51: "Sans espoir", 52: "Innocemment", 53: "Intensément",
    54: "Intéressamment", 55: "Irritant", 56: "Joyeusement", 57: "Avec gentillesse", 58: "Lâchement", 59: "Légèrement",
    60: "Lâchement", 61: "Fortement", 62: "Amoureusement", 63: "Loyalement", 64: "Majestueusement",
    65: "Significativement", 66: "Mécaniquement", 67: "Modérément", 68: "Misérablement", 69: "Moqueusement",
    70: "Mystérieusement", 71: "Naturellement", 72: "Soigneusement", 73: "Sympathiquement", 74: "Bizarrement",
    75: "Offensivement", 76: "Officiellement", 77: "Partiellement", 78: "Passivement", 79: "Pacifiquement",
    80: "Parfaitement", 81: "Ludiquement", 82: "Poliment", 83: "Positivement", 84: "Puissamment", 85: "Bizarrement",
    86: "Quarrellement", 87: "Silencieusement", 88: "Rugueusement", 89: "Grossièrement", 90: "Sans pitié",
    91: "Lentement", 92: "Doucement", 93: "Étrangement", 94: "Rapidement", 95: "Menaçant", 96: "Timidement",
    97: "Très", 98: "Violemment", 99: "Sauvagement", 100: "Souplement",
    101: "Anormal", 102: "Amusant", 103: "Artificiel", 104: "Moyenne", 105: "Beau", 106: "Bizarre", 107: "Ennuyeux",
    108: "Brillant", 109: "Cassé", 110: "Propre", 111: "Froid", 112: "Coloré", 113: "Incolore", 114: "Réconfortant",
    115: "Effrayant", 116: "Mignon", 117: "Endommagé", 118: "Sombre", 119: "Défait", 120: "Sale", 121: "Désagréable",
    122: "Sec", 123: "Ennuyeux", 124: "Vide", 125: "Énorme", 126: "Extraordinaire", 127: "Extravagant", 128: "Fané",
    129: "Familier", 130: "Chic", 131: "Faible", 132: "Festif", 133: "Parfait", 134: "Abandonné", 135: "Fragile",
    136: "Fragrant", 137: "Frais", 138: "Complet", 139: "Glorieux", 140: "Gracieux", 141: "Dur", 142: "Dur", 143: "Sain",
    144: "Lourd", 145: "Historique", 146: "Horrible", 147: "Important", 148: "Intéressant", 149: "Juvenile",
    150: "Manquant", 151: "Grand", 152: "Somptueux", 153: "Mince", 154: "Moins", 155: "Létal", 156: "Vivant",
    157: "Solitaire", 158: "Adorable", 159: "Magnifique", 160: "Mature", 161: "En désordre", 162: "Puissant",
    163: "Militaire", 164: "Moderne", 165: "Mundain", 166: "Mystérieux", 167: "Naturel", 168: "Normal", 169: "Bizarre",
    170: "Vieux", 171: "Pâle", 172: "Paisible", 173: "Petite", 174: "Simple", 175: "Pauvre", 176: "Puissant",
    177: "Protecteur", 178: "Charmant", 179: "Rare", 180: "Rassurant", 181: "Remarquable", 182: "Pourri", 183: "Rugueux",
    184: "Ruiné", 185: "Rustique", 186: "Effrayant", 187: "Choc", 188: "Simple", 189: "Petit", 190: "Lisse",
    191: "Doux", 192: "Fort", 193: "Élégant", 194: "Désagréable", 195: "Précieux", 196: "Vibrant", 197: "Chaud",
    198: "Aqueux", 199: "Faible", 200: "Jeune"
}

MEANING_ELEMENTS_CHARACTER = {
    1: "Accompagné", 2: "Actif", 3: "Agressif", 4: "Embuscade", 5: "Animal", 6: "Anxieux", 7: "Armé", 
    8: "Beau", 9: "Audacieux", 10: "Occupé", 11: "Calme", 12: "Négligent", 13: "Décontracté", 14: "Prudent", 
    15: "Classe", 16: "Coloré", 17: "Combattif", 18: "Fou", 19: "Effrayant", 20: "Curieux", 21: "Dangereux", 
    22: "Trompeur", 23: "Défait", 24: "Défiant", 25: "Délicieux", 26: "Émotionnel", 27: "Énergique", 
    28: "Équipé", 29: "Excité", 30: "Attendu", 31: "Familier", 32: "Rapide", 33: "Faible", 34: "Féminin", 
    35: "Féroce", 36: "Ennemi", 37: "Insensé", 38: "Chanceux", 39: "Fragrant", 40: "Frénétique", 41: "Ami", 
    42: "Effrayé", 43: "Effrayant", 44: "Généreux", 45: "Content", 46: "Heureux", 47: "Nocif", 48: "Utile", 
    49: "Impuissant", 50: "Blessé", 51: "Important", 52: "Inactif", 53: "Influenceur", 54: "Innocent", 
    55: "Intense", 56: "Savant", 57: "Grand", 58: "Solitaire", 59: "Bruyant", 60: "Loyal", 61: "Masculin", 
    62: "Puissant", 63: "Misérable", 64: "Multiple", 65: "Mundain", 66: "Mystérieux", 67: "Naturel", 
    68: "Bizarre", 69: "Officiel", 70: "Vieux", 71: "Passif", 72: "Paisible", 73: "Joueur", 74: "Puissant", 
    75: "Professionnel", 76: "Protégé", 77: "Protégeant", 78: "Questionnant", 79: "Silencieux", 80: "Rassurant", 
    81: "Ingénieux", 82: "Cherchant", 83: "Compétent", 84: "Lent", 85: "Petit", 86: "Discret", 87: "Étrange", 
    88: "Fort", 89: "Grand", 90: "Voleur", 91: "Menacant", 92: "Triomphant", 93: "Inattendu", 94: "Contre nature", 
    95: "Inhabituel", 96: "Violent", 97: "Vocal", 98: "Faible", 99: "Sauvage", 100: "Jeune"
}

MEANING_ELEMENTS_OBJECT = {
    1: "Actif", 2: "Artistique", 3: "Moyenne", 4: "Beau", 5: "Bizarre", 6: "Lumineux", 7: "Vêtements", 
    8: "Indice", 9: "Froid", 10: "Coloré", 11: "Communication", 12: "Compliqué", 13: "Confus", 14: "Consommable", 
    15: "Conteneur", 16: "Effrayant", 17: "Brut", 18: "Mignon", 19: "Endommagé", 20: "Dangereux", 
    21: "Désactivé", 22: "Délibéré", 23: "Délicieux", 24: "Désiré", 25: "Domestique", 26: "Vide", 27: "Énergie", 
    28: "Enorme", 29: "Équipement", 30: "Attendu", 31: "Expiré", 32: "Extravagant", 33: "Fané", 34: "Familier", 
    35: "Chic", 36: "Flore", 37: "Chanceux", 38: "Fragile", 39: "Fragrant", 40: "Effrayant", 41: "Poubelle", 
    42: "Orientation", 43: "Dur", 44: "Nocif", 45: "Guérison", 46: "Lourd", 47: "Utile", 48: "Horrible", 
    49: "Important", 50: "Inactif", 51: "Information", 52: "Intrigant", 53: "Grand", 54: "Létal", 55: "Léger", 
    56: "Liquide", 57: "Bruyant", 58: "Majestueux", 59: "Significatif", 60: "Mécanique", 61: "Moderne", 
    62: "Mobile", 63: "Multiple", 64: "Mundain", 65: "Mystérieux", 66: "Naturel", 67: "Nouveau", 68: "Bizarre", 
    69: "Officiel", 70: "Vieux", 71: "Ornemental", 72: "Orné", 73: "Personnel", 74: "Puissant", 75: "Prisé", 
    76: "Ration", 77: "Saison", 78: "Secrétaire", 79: "Sensible", 80: "Solide", 81: "Délicat", 82: "Protecteur", 
    83: "Survie", 84: "Silencieux", 85: "Savant", 86: "Triomphal", 87: "Transport", 88: "Utile", 89: "Vanité", 
    90: "Tempête", 91: "Vieux", 92: "Trop", 93: "Protéger", 94: "Poids", 95: "Respecté", 96: "Solitaire", 
    97: "Sensible", 98: "Forcément", 99: "Voleur", 100: "Spécial"
}


CHARACTERE_ACTIONS_COMBAT = {
    1: "Abandonner", 2: "Abuser", 3: "Agressif", 4: "Accepter", 5: "Allier", 
    6: "Attaquer en embuscade", 7: "Amuser", 8: "Colère", 9: "Antagoniser", 10: "Anxieux", 
    11: "Aider", 12: "Attaquer", 13: "Trahir", 14: "Bloquer", 15: "Audacieux", 16: "Brave", 
    17: "Casser", 18: "Calme", 19: "Négligent", 20: "Porter", 21: "Prudent", 22: "Célébrer", 
    23: "Changer", 24: "Charger", 25: "Communiquer", 26: "Compétitionner", 27: "Contrôler", 
    28: "Fou", 29: "Cruel", 30: "Dégâts", 31: "Tromper", 32: "Défendre", 33: "Défiant", 
    34: "Retarder", 35: "Perturber", 36: "Diviser", 37: "Dominer", 38: "Énergique", 
    39: "Enthousiaste", 40: "Attente", 41: "Peur", 42: "Féroce", 43: "Vif", 44: "Combattre", 
    45: "Fuir", 46: "Frénétique", 47: "Libérer", 48: "Effrayant", 49: "Faire du mal", 
    50: "Sévère", 51: "Précipité", 52: "Cacher", 53: "Imiter", 54: "Emprisonner", 55: "Tuer", 
    56: "Diriger", 57: "Létal", 58: "Liberté", 59: "Mentir", 60: "Fort", 61: "Loyal", 
    62: "Magie", 63: "Mécanique", 64: "Puissant", 65: "Militaire", 66: "Se moquer", 67: "Bouger", 
    68: "Mystérieux", 69: "Normal", 70: "Bizarre", 71: "Ouvrir", 72: "S'opposer", 73: "Douleur", 
    74: "Chemin", 75: "Préparer", 76: "Punir", 77: "Poursuivre", 78: "Rough", 79: "Grossier", 
    80: "Ruiner", 81: "Implacable", 82: "Simple", 83: "Lent", 84: "Espionner", 85: "Arrêter", 
    86: "Bizarre", 87: "Lutter", 88: "Supprimer", 89: "Rapide", 90: "Prendre", 91: "Technologie", 
    92: "Menacer", 93: "Trick", 94: "Trêve", 95: "Usurper", 96: "Véhicule", 97: "Vengeance", 
    98: "Gaspiller", 99: "Arme", 100: "Retirer"
}


CHARACTERE_ACTIONS_GENERAL = {
    1: "Abandonner", 2: "Agressif", 3: "Amusant", 4: "Colère", 5: "Antagoniser", 
    6: "Anxieux", 7: "Aider", 8: "Accorder", 9: "Trahir", 10: "Bizarre", 11: "Bloquer", 
    12: "Audacieux", 13: "Casser", 14: "Calme", 15: "Soin", 16: "Prudent", 17: "Négligent", 
    18: "Célébrer", 19: "Changer", 20: "Combatif", 21: "Communiquer", 22: "Contrôler", 
    23: "Fou", 24: "Étrange", 25: "Dangereux", 26: "Tromper", 27: "Diminuer", 28: "Défiant", 
    29: "Retarder", 30: "Perturber", 31: "Dominer", 32: "Efficace", 33: "Énergique", 
    34: "Excité", 35: "Exposer", 36: "Peur", 37: "Faible", 38: "Féroce", 39: "Combattre", 
    40: "Insensé", 41: "Frénétique", 42: "Effrayant", 43: "Généreux", 44: "Doux", 45: "Faire du mal", 
    46: "Sévère", 47: "Précipité", 48: "Utile", 49: "Imiter", 50: "Important", 51: "Emprisonner", 
    52: "Augmenter", 53: "Inspecter", 54: "Intense", 55: "Juvenile", 56: "Gentil", 57: "Paresseux", 
    58: "Leadership", 59: "Létal", 60: "Fort", 61: "Loyal", 62: "Mature", 63: "Significatif", 
    64: "Désordonné", 65: "Bouger", 66: "Mundane", 67: "Mystérieux", 68: "Sympa", 69: "Normal", 
    70: "Bizarre", 71: "Officiel", 72: "Ouvrir", 73: "S'opposer", 74: "Passion", 75: "Paix", 
    76: "Joueur", 77: "Plaisirs", 78: "Possessions", 79: "Punir", 80: "Poursuivre", 81: "Libérer", 
    82: "Retour", 83: "Simple", 84: "Lent", 85: "Commencer", 86: "Arrêter", 87: "Bizarre", 
    88: "Lutter", 89: "Rapide", 90: "Tactiques", 91: "Prendre", 92: "Technologie", 93: "Menacer", 
    94: "Confiance", 95: "Violent", 96: "Gaspiller", 97: "Armes", 98: "Sauvage", 99: "Travail", 
    100: "Céder"
}


CHARACTERE_APPARENCE = {
    1: "Anormal", 2: "Arme", 3: "Aromatique", 4: "Athlétique", 5: "Attrayant", 
    6: "Moyenne", 7: "Chauve", 8: "Belle", 9: "Bizarre", 10: "Brutal", 11: "Décontracté", 
    12: "Classe", 13: "Propre", 14: "Vêtements", 15: "Coloré", 16: "Commun", 17: "Cool", 
    18: "Effrayant", 19: "Mignon", 20: "Gracieux", 21: "Délicat", 22: "Désespéré", 23: "Différent", 
    24: "Sale", 25: "Monotone", 26: "Élégant", 27: "Équipement", 28: "Exotique", 29: "Cher", 
    30: "Extravagant", 31: "Lunettes", 32: "Familier", 33: "Chic", 34: "Caractéristiques", 
    35: "Féminin", 36: "Festif", 37: "Fragile", 38: "Cheveux", 39: "Poilu", 40: "Coiffure", 
    41: "Lourd", 42: "Blessé", 43: "Innocent", 44: "Insigne", 45: "Intense", 46: "Intéressant", 
    47: "Intimidant", 48: "Bijoux", 49: "Grand", 50: "Somptueux", 51: "Mince", 52: "Membres", 
    53: "Lithe", 54: "Masculin", 55: "Mature", 56: "Désordonné", 57: "Puissant", 58: "Moderne", 
    59: "Mundane", 60: "Musclé", 61: "Mystérieux", 62: "Naturel", 63: "Soigné", 64: "Normal", 
    65: "Bizarre", 66: "Officiel", 67: "Vieux", 68: "Petit", 69: "Perçant", 70: "Puissant", 
    71: "Professionnel", 72: "Rassurant", 73: "Régale", 74: "Remarquable", 75: "Rough", 
    76: "Rustique", 77: "Cicatrice", 78: "Effrayant", 79: "Scenté", 80: "Savant", 81: "Court", 
    82: "Simple", 83: "Sinistre", 84: "Petit", 85: "Puant", 86: "Trapu", 87: "Étrange", 
    88: "Détendu", 89: "Pauvre", 90: "Grande", 91: "Vieux", 92: "Mignon", 93: "Sombre", 
    94: "Petit", 95: "Excentrique", 96: "Silencieux", 97: "Salissant", 98: "Pauvre", 99: "Féminine", 
    100: "Agé"
}


CHARACTER_IDENTITY = {
    1: "Abandonné", 2: "Administrateur", 3: "Aventurier", 4: "Adversaire", 5: "Conseiller",
    6: "Allié", 7: "Art", 8: "Artiste", 9: "Assistant", 10: "Athlète", 11: "Autorité",
    12: "Bureaucrate", 13: "Affaires", 14: "Combattant", 15: "Concurrent", 16: "Contrôleur",
    17: "Artisan", 18: "Créateur", 19: "Criminel", 20: "Trompeur", 21: "Livreur", 
    22: "Dépendant", 23: "Conducteur/Pilote", 24: "Élite", 25: "Ennemi", 26: "Exécuteur", 
    27: "Ingénieur", 28: "Divertisseur", 29: "Exécutif", 30: "Expert", 31: "Explorateur", 
    32: "Famille", 33: "Agriculteur", 34: "Combattant", 35: "Réparateur", 36: "Étranger", 
    37: "Ami", 38: "Parieur", 39: "Récolteur", 40: "Gardien", 41: "Guérisseur", 
    42: "Impuissant", 43: "Héros", 44: "Chasseur", 45: "Information", 46: "Innocent", 
    47: "Inspecteur", 48: "Intellectuel", 49: "Investigateur", 50: "Juge", 
    51: "Meurtrier", 52: "Ouvrier", 53: "Domestique", 54: "Loi", 55: "Leader", 
    56: "Légal", 57: "Perdu", 58: "Mécanique", 59: "Médiateur", 60: "Marchand", 
    61: "Messager", 62: "Militaire", 63: "Mundain", 64: "Mystère", 65: "Officiel", 
    66: "Organisateur", 67: "Étranger", 68: "Performer", 69: "Persécuteur", 
    70: "Planificateur", 71: "Plaire", 72: "Pouvoir", 73: "Prisonnier", 74: "Professionnel", 
    75: "Protecteur", 76: "Public", 77: "Punir", 78: "Radical", 79: "Religieux", 
    80: "Représenter", 81: "Voleur", 82: "Vaurien", 83: "Dirigeant", 84: "Érudit", 
    85: "Scientifique", 86: "Éclaireur", 87: "Servant", 88: "Socialite", 89: "Soldat", 
    90: "Étudiant", 91: "Subversif", 92: "Soutien", 93: "Survivant", 94: "Professeur", 
    95: "Voleur", 96: "Commerçant", 97: "Victime", 98: "Méchant", 99: "Vagabond", 
    100: "Guerrier"
}


CHARACTER_MOTIVATIONS = {
    1: "Aventure", 2: "Adversité", 3: "Ambition", 4: "Colère", 5: "Approbation", 
    6: "Art", 7: "Atteindre", 8: "Affaires", 9: "Changement", 10: "Caractère", 
    11: "Conflit", 12: "Contrôler", 13: "Créer", 14: "Danger", 15: "Mort", 16: "Tromper", 
    17: "Détruire", 18: "Diminuer", 19: "Perturber", 20: "Émotion", 21: "Ennemi", 
    22: "Environnement", 23: "Évasion", 24: "Échec", 25: "Gloire", 26: "Famille", 
    27: "Peur", 28: "Combattre", 29: "Trouver", 30: "Libérer", 31: "Ami", 
    32: "Objectif", 33: "Satisfaire", 34: "Groupe", 35: "Guider", 36: "Culpabilité", 
    37: "Haine", 38: "Guérir", 39: "Aider", 40: "Cacher", 41: "Maison", 42: "Espoir", 
    43: "Idée", 44: "Maladie", 45: "Important", 46: "Emprisonner", 47: "Augmenter", 
    48: "Information", 49: "Innocent", 50: "Intellect", 51: "Intolérance", 
    52: "Investissement", 53: "Jalousie", 54: "Joie", 55: "Justice", 56: "Leader", 
    57: "Légal", 58: "Perte", 59: "Amour", 60: "Loyauté", 61: "Malice", 62: "Malheur", 
    63: "Méfiance", 64: "Mundain", 65: "Mystérieux", 66: "Nature", 67: "Objet", 
    68: "Obligation", 69: "Officiel", 70: "S'opposer", 71: "Douleur", 72: "Passion", 
    73: "Chemin", 74: "Paix", 75: "Physique", 76: "Lieu", 77: "Plan", 78: "Plaisir", 
    79: "Pouvoir", 80: "Fierté", 81: "Protéger", 82: "Poursuivre", 83: "Rare", 
    84: "Récupérer", 85: "Révéler", 86: "Revanche", 87: "Richesses", 88: "Sécurité", 
    89: "Recherche", 90: "Servir", 91: "Commencer", 92: "Arrêter", 93: "Étrange", 
    94: "Lutter", 95: "Succès", 96: "Souffrance", 97: "Soutenir", 98: "Prendre", 
    99: "Transformer", 100: "Voyager"
}


CHARACTER_PERSONALITY = {
    1: "Actif", 2: "Aventurier", 3: "Agressif", 4: "Agréable", 5: "Ambitieux", 
    6: "Amusant", 7: "Colérique", 8: "Ennuyant", 9: "Anxieux", 10: "Arrogant", 
    11: "Moyenne", 12: "Maladroit", 13: "Mauvais", 14: "Amer", 15: "Audacieux", 
    16: "Courageux", 17: "Calme", 18: "Prudent", 19: "Négligent", 20: "Classe", 
    21: "Froid", 22: "Collectionneur", 23: "Engagé", 24: "Compétitif", 25: "Confiant", 
    26: "Contrôle", 27: "Fou", 28: "Créatif", 29: "Rudimentaire", 30: "Curieux", 
    31: "Trompeur", 32: "Déterminé", 33: "Dévoué", 34: "Désagréable", 35: "Ennuyeux", 
    36: "Émotionnel", 37: "Empathique", 38: "Juste", 39: "Pointilleux", 40: "Suiveur", 
    41: "Fou", 42: "Amical", 43: "Bon", 44: "Gourmet", 45: "Gourmand", 46: "Hanté", 
    47: "Utile", 48: "Honnête", 49: "Honneur", 50: "Humble", 51: "Humoristique", 
    52: "Inconsistant", 53: "Indépendant", 54: "Intéressant", 55: "Intolérant", 
    56: "Irresponsable", 57: "Connaisseur", 58: "Larcin", 59: "Loyal", 60: "Médiocre", 
    61: "Méprisant", 62: "Nerveux", 63: "Optimiste", 64: "Réaliste", 65: "Ressentiment", 
    66: "Intéressé", 67: "Exigeant", 68: "Secret", 69: "Sensible", 70: "Sociable", 
    71: "Suffisant", 72: "Gentil", 73: "Maniaque", 74: "Vulnérable", 75: "Légèrement", 
    76: "Grincheux", 77: "Patient", 78: "Négatif", 79: "Prudent", 80: "Psychotique", 
    81: "Respectueux", 82: "Pragmatique", 83: "Romantique", 84: "Inflexible", 
    85: "Sociable", 86: "Stupide", 87: "Timide", 88: "Tactile", 89: "Vainqueur", 
    90: "Vantard", 91: "Violent", 92: "Vulnerable", 93: "Zélé", 94: "Délicat", 
    95: "Bénéfique", 96: "Serieux", 97: "Tendre", 98: "Utopiste", 99: "Zélé", 
    100: "Égoïste"
}


CHARACTER_SKILLS = {
    1: "Activité", 2: "Adversité", 3: "Agilité", 4: "Animaux", 5: "Art",
    6: "Assistance", 7: "Athlétisme", 8: "Attaque", 9: "Atteindre", 10: "Moyenne",
    11: "Équilibre", 12: "Débutant", 13: "Octroyer", 14: "Bloquer", 15: "Affaires",
    16: "Changement", 17: "Combat", 18: "Communiquer", 19: "Conflit", 20: "Contrôle",
    21: "Créer", 22: "Criminel", 23: "Dégâts", 24: "Danger", 25: "Duperie", 
    26: "Diminuer", 27: "Défense", 28: "Développer", 29: "Dispute", 30: "Perturber", 
    31: "Domestique", 32: "Dominer", 33: "Conduite", 34: "", 35: "Énergie", 
    36: "Environnement", 37: "Expérimenté", 38: "Expert", 39: "Se battre", 40: "Libre", 
    41: "Guider", 42: "Nuire", 43: "Guérir", 44: "Santé", 45: "Augmenter", 
    46: "Informer", 47: "Information", 48: "Enquêter", 49: "Inspecter", 50: "Intellect", 
    51: "Envahir", 52: "Investigatif", 53: "Connaissances", 54: "Leadership", 
    55: "Légal", 56: "Létal", 57: "Mentir", 58: "Maître", 59: "Mécanique", 
    60: "Médical", 61: "Mental", 62: "Militaire", 63: "Mouvement", 64: "Se déplacer", 
    65: "Ordinaire", 66: "Mystérieux", 67: "Nature", 68: "Normal", 69: "Obstacles", 
    70: "Officiel", 71: "Ouvrir", 72: "Opposer", 73: "Perception", 74: "Pratique", 
    75: "Professionnel", 76: "À distance", 77: "Libérer", 78: "Voleur", 79: "Ruine", 
    80: "Simple", 81: "Social", 82: "Spécialiste", 83: "Commencer", 84: "Arrêter", 
    85: "Étrange", 86: "Force", 87: "Lutter", 88: "Supprimer", 89: "Prendre", 
    90: "Technologie", 91: "Transformer", 92: "Voyager", 93: "Tromper", 94: "Usurper", 
    95: "Véhicule", 96: "Violence", 97: "Eau", 98: "Arme", 99: "Temps", 
    100: "Blessures"
}


CHARACTER_TRAITS_FLAWS = {
    1: "Académique", 2: "Adversité", 3: "Animal", 4: "Assistance", 5: "Attirer", 
    6: "Beau", 7: "Bénéfices", 8: "Octroyer", 9: "Bizarre", 10: "Bloquer", 
    11: "Fardeau", 12: "Combat", 13: "Communiquer", 14: "Connexion", 15: "Contrôler", 
    16: "Créer", 17: "Criminel", 18: "Endommagé", 19: "Dangereux", 20: "Diminuer", 
    21: "Défense", 22: "Délicat", 23: "Différent", 24: "Dominer", 25: "Motivé", 
    26: "Émotion", 27: "Ennemi", 28: "Énergie", 29: "Environnement", 30: "Échec", 
    31: "Célébrité", 32: "Familier", 33: "Rapide", 34: "Faible", 35: "Sans défaut", 
    36: "Concentré", 37: "Fortuné", 38: "Amis", 39: "Bon", 40: "Sain", 
    41: "Maladie", 42: "Altéré", 43: "Augmenter", 44: "Information", 45: "Inspecter", 
    46: "Intellect", 47: "Intense", 48: "Intéressant", 49: "Manquant", 50: "Grand", 
    51: "Leadership", 52: "Légal", 53: "Moins", 54: "Létal", 55: "Limité", 
    56: "Loyal", 57: "Mental", 58: "Militaire", 59: "Malchance", 60: "Manquant", 
    61: "Se déplacer", 62: "Multi", 63: "Nature", 64: "Objet", 65: "Bizarre", 
    66: "Vieux", 67: "Partiel", 68: "Passion", 69: "Perception", 70: "Physique", 
    71: "Pauvre", 72: "Biens", 73: "Pouvoir", 74: "Principes", 75: "Public", 
    76: "Rare", 77: "Remarquable", 78: "Résistant", 79: "Ressource", 80: "Riche", 
    81: "Sens", 82: "Compétence", 83: "Petit", 84: "Social", 85: "Spécialisé", 
    86: "Esprit", 87: "Étrange", 88: "Fort", 89: "Souffrance", 90: "Technique", 
    91: "Technologie", 92: "Solide", 93: "Voyage", 94: "Problème", 95: "Digne de confiance", 
    96: "Inhabituel", 97: "Très", 98: "Faible", 99: "Arme", 100: "Jeune"
}


CITY_DESCRIPTORS = {
    1: "Activité", 2: "Agressif", 3: "Aromatique", 4: "Moyenne", 5: "Beau", 
    6: "Morne", 7: "Bloc", 8: "Pont", 9: "Bourdonner", 10: "Calme", 
    11: "Chaotique", 12: "Propre", 13: "Froid", 14: "Coloré", 15: "Commerce", 
    16: "Conflit", 17: "Contrôle", 18: "Crime", 19: "Dangereux", 20: "Dense", 
    21: "Développé", 22: "Sale", 23: "Efficace", 24: "Énergie", 25: "Énorme", 
    26: "Environnement", 27: "Extravagant", 28: "Festif", 29: "Sans défaut", 
    30: "Effrayant", 31: "Gouvernement", 32: "Heureux", 33: "Dur", 34: "Sain", 
    35: "Utile", 36: "Collines", 37: "Histoire", 38: "Maladie", 39: "Important", 
    40: "Impressionnant", 41: "Industrie", 42: "Intéressant", 43: "Intrigues", 
    44: "Isolé", 45: "Manquant", 46: "Lac", 47: "Grand", 48: "Somptueux", 
    49: "Leadership", 50: "Liberté", 51: "Bruyant", 52: "Magnifique", 53: "Masses", 
    54: "Significatif", 55: "Mécanique", 56: "Encombré", 57: "Puissant", 
    58: "Militaire", 59: "Misérable", 60: "Malchance", 61: "Moderne", 62: "Montagne", 
    63: "Ordinaire", 64: "Mystérieux", 65: "Nature", 66: "Bizarre", 67: "Vieux", 
    68: "Oppression", 69: "Opulence", 70: "Paix", 71: "Pauvre", 72: "Puissant", 
    73: "Protégé", 74: "Public", 75: "Calme", 76: "Rare", 77: "Rassurant", 
    78: "Remarquable", 79: "Rivière", 80: "Rough", 81: "Ruiné", 82: "Rustique", 
    83: "Simple", 84: "Petit", 85: "Clairsemé", 86: "Structures", 87: "Lutte", 
    88: "Succès", 89: "Souffrance", 90: "Technologie", 91: "Tension", 
    92: "Voyager", 93: "Troublé", 94: "Précieux", 95: "Chaud", 96: "Eau", 
    97: "Faible", 98: "Météo", 99: "Sauvage", 100: "Travail"
}


DESCRIPTEURS_CIVILISATION = {
    1: "Actif", 2: "Avancé", 3: "Aventureux", 4: "Agressif", 5: "Agricole",
    6: "Ancien", 7: "En colère", 8: "Anxieux", 9: "Artistique", 10: "Moyen",
    11: "Beau", 12: "Bizarre", 13: "Sombre", 14: "Audacieux", 15: "Bureaucratique",
    16: "Insouciant", 17: "Prudent", 18: "Négligent", 19: "Précautionneux", 20: "Chic",
    21: "Propre", 22: "Coloré", 23: "Combatif", 24: "Commercial", 25: "Compétitif",
    26: "Constructif", 27: "Contrôlant", 28: "Fou", 29: "Créatif", 30: "Effrayant",
    31: "Cruel", 32: "Curieux", 33: "Dangereux", 34: "En déclin", 35: "Défiant",
    36: "Délicieux", 37: "Développé", 38: "Désagréable", 39: "Méfiant", 40: "Dominant",
    41: "Ennuyant", 42: "Efficace", 43: "En expansion", 44: "Échoué", 45: "Célèbre",
    46: "Craintif", 47: "Festif", 48: "Libre", 49: "Généreux", 50: "Avide",
    51: "Heureux", 52: "Sain", 53: "Serviable", 54: "Impuissant", 55: "Historique",
    56: "Important", 57: "Industriel", 58: "Influent", 59: "Intolérant", 60: "Grand",
    61: "Légal", 62: "Sans loi", 63: "Magnifique", 64: "Puissant", 65: "Militariste",
    66: "Misérable", 67: "Moderne", 68: "Mundane", 69: "Mystérieux", 70: "Vieux",
    71: "Ouvert", 72: "Oppressif", 73: "Paisible", 74: "Poli", 75: "Pauvre",
    76: "Puissant", 77: "Primitif", 78: "Punitif", 79: "Pittoresque", 80: "Religieux",
    81: "Ruine", 82: "Rustique", 83: "Impitoyable", 84: "Effrayant", 85: "Simple",
    86: "Petit", 87: "Étrange", 88: "Fort", 89: "Luttant", 90: "Réussi",
    91: "Souffrant", 92: "Réprimé", 93: "Suspicieux", 94: "Traître", 95: "Belliqueux",
    96: "Faible", 97: "Riche", 98: "Accueillant", 99: "Sauvage", 100: "Jeune"
}


CAPACITÉS_CRÉATURE = {
    1: "Embuscade", 2: "Animer", 3: "Armure", 4: "Arriver", 5: "Attacher",
    6: "Attaquer", 7: "Attirer", 8: "Mordre", 9: "Bloquer", 10: "Émousser",
    11: "Casser", 12: "Souffle", 13: "Porter", 14: "Changer", 15: "Grimper",
    16: "Froid", 17: "Commun", 18: "Communiquer", 19: "Cacher", 20: "Contacter",
    21: "Contrôler", 22: "Créer", 23: "Endommager", 24: "Sombre", 25: "Mort",
    26: "Tromper", 27: "Diminuer", 28: "Défense", 29: "Dépouvoir", 30: "Détecter",
    31: "Perturber", 32: "Distraire", 33: "Dominer", 34: "Drainer", 35: "Élément",
    36: "Énergie", 37: "Amélioré", 38: "Enchevêtrer", 39: "Environnement", 40: "Extra",
    41: "Peur", 42: "Combattre", 43: "Feu", 44: "Vol", 45: "Nuire",
    46: "Guérir", 47: "Maladie", 48: "Illusion", 49: "Imiter", 50: "Immunisé",
    51: "Emprisonner", 52: "Augmenter", 53: "Intelligent", 54: "Lui-même", 55: "Létal",
    56: "Lumière", 57: "Limité", 58: "Esprit", 59: "Bouger", 60: "Multiple",
    61: "Naturel", 62: "Normal", 63: "Ouvrir", 64: "Autres", 65: "Paralyser",
    66: "Physique", 67: "Percer", 68: "Poison", 69: "Pouvoir", 70: "Protection",
    71: "Proximité", 72: "Poursuivre", 73: "À distance", 74: "Rechargeable", 75: "Résistance",
    76: "Autonome", 77: "Sens", 78: "Compétence", 79: "Dormir", 80: "Vitesse",
    81: "Espionner", 82: "Furtivité", 83: "Arrêter", 84: "Étrange", 85: "Étourdir",
    86: "Substance", 87: "Invoquer", 88: "Supprimer", 89: "Nager", 90: "Prendre",
    91: "Télépathie", 92: "Toucher", 93: "Transformer", 94: "Voyager", 95: "Tromper",
    96: "Inhabituel", 97: "Vision", 98: "Vulnérable", 99: "Faible", 100: "Arme"
}


DESCRIPTEURS_CRÉATURE = {
    1: "Agressif", 2: "Agile", 3: "Air", 4: "Alien", 5: "Amorphe",
    6: "Animal", 7: "Aquatique", 8: "Blindé", 9: "Aviaire", 10: "Bête",
    11: "Beau", 12: "Corps", 13: "Osseux", 14: "Carapace", 15: "Griffu",
    16: "Vêtu", 17: "Froid", 18: "Couleur", 19: "Composite", 20: "Construit",
    21: "Délabré", 22: "Défensif", 23: "Dégoulinant", 24: "", 25: "Exotique",
    26: "Membres supplémentaires", 27: "Crocs", 28: "Féminin", 29: "Féral", 30: "Sale",
    31: "Feu", 32: "Fongique", 33: "Poilu", 34: "Décharné", 35: "Lumineux",
    36: "Groupe", 37: "Grondeur", 38: "Sain", 39: "Cornes", 40: "Humanoïde",
    41: "Inscrit", 42: "Insectoïde", 43: "Insubstantiel", 44: "Intelligent", 45: "Intimidant",
    46: "Grand", 47: "Lévitation", 48: "Limité", 49: "Liquide", 50: "Bruyant",
    51: "Mammifère", 52: "Mandibules", 53: "Masculin", 54: "Mécanique", 55: "Métallique",
    56: "Mouvement", 57: "Multiple", 58: "Mutant", 59: "Naturel", 60: "Nature",
    61: "Cauchemardesque", 62: "Objet", 63: "Odorant", 64: "Passif", 65: "Plante",
    66: "Reptilien", 67: "Robotique", 68: "Enraciné", 69: "Rugueux", 70: "Forme",
    71: "Changeant", 72: "Silencieux", 73: "Simple", 74: "Svelte", 75: "Petit",
    76: "Solitaire", 77: "Arachnéen", 78: "Épineux", 79: "Vapeur", 80: "Collant",
    81: "Dard", 82: "Étrange", 83: "Fort", 84: "Surnaturel", 85: "Queue",
    86: "Tentaculaire", 87: "Langue", 88: "Denté", 89: "Transparent", 90: "Arboré",
    91: "Tordu", 92: "Mort-vivant", 93: "Non naturel", 94: "Verbal", 95: "Chaud",
    96: "Faible", 97: "Arme", 98: "Ailes", 99: "Boisé", 100: "Vermiforme"
}


MESSAGE_CRYPTIQUE = {
    1: "Abandonné", 2: "Activité", 3: "Aventure", 4: "Adversité", 5: "Conseil",
    6: "Alliés", 7: "Colère", 8: "Conférer", 9: "Trahir", 10: "Bizarre",
    11: "Sombre", 12: "Affaires", 13: "Soin", 14: "Coloré", 15: "Communiquer",
    16: "Conflit", 17: "Effrayant", 18: "Endommagé", 19: "Danger", 20: "Mort",
    21: "Tromper", 22: "Défiant", 23: "Dispute", 24: "Diviser", 25: "Émotions",
    26: "Ennemis", 27: "Environnement", 28: "Mal", 29: "Exposer", 30: "Échec",
    31: "Renommée", 32: "Peur", 33: "Combattre", 34: "Frénétique", 35: "Libre",
    36: "Amitié", 37: "Objectifs", 38: "Bon", 39: "Guide", 40: "Nuire",
    41: "Aider", 42: "Utile", 43: "Caché", 44: "Espoir", 45: "Horrible",
    46: "Important", 47: "Information", 48: "Innocent", 49: "Instruction", 50: "Intrigues",
    51: "Langue", 52: "Leadership", 53: "Légal", 54: "Légende", 55: "Liberté",
    56: "Mensonges", 57: "Perdu", 58: "Amour", 59: "Malveillance", 60: "Désordonné",
    61: "Malchance", 62: "Méfiance", 63: "Bouger", 64: "Mundane", 65: "Mystérieux",
    66: "Négliger", 67: "Normal", 68: "Obscurci", 69: "Officiel", 70: "Vieux",
    71: "S'opposer", 72: "Partiel", 73: "Passion", 74: "Plans", 75: "Possessions",
    76: "Pouvoir", 77: "Proposer", 78: "Punir", 79: "Poursuivre", 80: "Rare",
    81: "Rassurant", 82: "Destinataire", 83: "Révéler", 84: "Richesses", 85: "Énigme",
    86: "Rumeur", 87: "Secret", 88: "Commencer", 89: "Arrêter", 90: "Étrange",
    91: "Lutte", 92: "Succès", 93: "Tension", 94: "Menacer", 95: "Trêve",
    96: "Confiance", 97: "Inconnu", 98: "Vengeance", 99: "Violence", 100: "Avertissement"
}


MALEDICTIONS = {
    1: "Abandonner", 2: "Vieillir", 3: "Attirer", 4: "Mauvais", 5: "Beauté",
    6: "Trahir", 7: "Bizarre", 8: "Bloquer", 9: "Corps", 10: "Casser",
    11: "Fardeau", 12: "Affaires", 13: "Changer", 14: "Contraindre", 15: "Condamner",
    16: "Conflit", 17: "Créer", 18: "Effrayant", 19: "Cruel", 20: "Danger",
    21: "Mort", 22: "Diminuer", 23: "Retarder", 24: "Perturber", 25: "Diviser",
    26: "Dominer", 27: "Rêves", 28: "", 29: "Émotions", 30: "Ennemis",
    31: "Énergie", 32: "Environnement", 33: "Mal", 34: "Échec", 35: "Renommée",
    36: "Famille", 37: "Destin", 38: "Peur", 39: "Faible", 40: "Combattre",
    41: "Amis", 42: "Effrayant", 43: "Objectifs", 44: "Bon", 45: "Satisfaire",
    46: "Guide", 47: "Bonheur", 48: "Nuire", 49: "Santé", 50: "Impuissant",
    51: "Maison", 52: "Maladie", 53: "Illusions", 54: "Emprisonner", 55: "Incapacité",
    56: "Information", 57: "Intellect", 58: "Ironique", 59: "Jalousie", 60: "Joie",
    61: "Légal", 62: "Létal", 63: "Liberté", 64: "Limiter", 65: "Solitaire",
    66: "Amour", 67: "Chance", 68: "Malveillance", 69: "Significatif", 70: "Misérable",
    71: "Malchance", 72: "Méfiance", 73: "Se moquer", 74: "Bouger", 75: "Mundane",
    76: "Mystérieux", 77: "Nature", 78: "Négliger", 79: "Vieux", 80: "Opprimer",
    81: "Douleur", 82: "Passion", 83: "Paix", 84: "Permanent", 85: "Possessions",
    86: "Punir", 87: "Poursuivre", 88: "Richesses", 89: "Ruiner", 90: "Sens",
    91: "Séparer", 92: "Commencer", 93: "Arrêter", 94: "Étrange", 95: "Lutte",
    96: "Succès", 97: "Temporaire", 98: "Vengeance", 99: "Violence", 100: "Arme"
}


DESCRIPTEURS_DOMICILE = {
    1: "Abandonné", 2: "Activité", 3: "Animal", 4: "Aromatique", 5: "Art",
    6: "Moyen", 7: "Beau", 8: "Bizarre", 9: "Sombre", 10: "Occupé",
    11: "Chic", 12: "Propre", 13: "Encombré", 14: "Froid", 15: "Coloré",
    16: "Confort", 17: "Commun", 18: "Exigu", 19: "Effrayant", 20: "Bondé",
    21: "Personnalisé", 22: "Mignon", 23: "Endommagé", 24: "Dangereux", 25: "Sombre",
    26: "Désolé", 27: "Différent", 28: "Sale", 29: "Désagréable", 30: "Terne",
    31: "Ennuyant", 32: "Vide", 33: "Énorme", 34: "Attendu", 35: "Extravagant",
    36: "Fané", 37: "Fantaisie", 38: "Festif", 39: "Nourriture", 40: "Effrayant",
    41: "Plein", 42: "Maison", 43: "Investissement", 44: "Invitant", 45: "Manquant",
    46: "Grand", 47: "Somptueux", 48: "Moins", 49: "Lumière", 50: "Bruyant",
    51: "Magnifique", 52: "Mécanique", 53: "Désordonné", 54: "Moderne", 55: "Mundane",
    56: "Mystérieux", 57: "Naturel", 58: "Net", 59: "Négligé", 60: "Indescriptible",
    61: "Normal", 62: "Occupé", 63: "Étrange", 64: "Ouvert", 65: "Oppressif",
    66: "Opulent", 67: "Organisé", 68: "Plantes", 69: "Pauvre", 70: "Portail",
    71: "Possessions", 72: "Privé", 73: "Protection", 74: "Pittoresque", 75: "Rassurant",
    76: "Spacieux", 77: "Rugueux", 78: "Ruine", 79: "Rustique", 80: "Effrayant",
    81: "Sécurisé", 82: "Sécurité", 83: "Simple", 84: "Dormir", 85: "Petit",
    86: "Malodorant", 87: "Épars", 88: "Stockage", 89: "Étrange", 90: "Temporaire",
    91: "Plein de pensées", 92: "Ordonné", 93: "Outils", 94: "Tranquille", 95: "Amélioration",
    96: "Utilitaire", 97: "Objets de valeur", 98: "Vue", 99: "Chaud", 100: "Eau"
}


DESCRIPTEURS_DONJON = {
    1: "Abandonné", 2: "Activité", 3: "Adversité", 4: "Embuscade", 5: "Ancien",
    6: "Animal", 7: "Aromatique", 8: "Art", 9: "Beau", 10: "Bizarre",
    11: "Sombre", 12: "Chambre", 13: "Propre", 14: "Fermé", 15: "Froid",
    16: "Effondré", 17: "Coloré", 18: "Créature", 19: "Effrayant", 20: "Endommagé",
    21: "Danger", 22: "Sombre", 23: "Désolé", 24: "Sale", 25: "Porte",
    26: "Sec", 27: "", 28: "Vide", 29: "Rencontre", 30: "Ennemis",
    31: "Énorme", 32: "Mal", 33: "Sortie", 34: "Extravagant", 35: "Fané",
    36: "Familier", 37: "Fantaisie", 38: "Peur", 39: "Présage", 40: "Plein",
    41: "Mobilier", 42: "Porte", 43: "Bon", 44: "Nuire", 45: "Lourd",
    46: "Utile", 47: "Trou", 48: "Important", 49: "Information", 50: "Intéressant",
    51: "Grand", 52: "Somptueux", 53: "Létal", 54: "Lumière", 55: "Magnifique",
    56: "Malveillance", 57: "Significatif", 58: "Mécanique", 59: "Messages", 60: "Désordonné",
    61: "Puissant", 62: "Militaire", 63: "Malchance", 64: "Moderne", 65: "Mundane",
    66: "Mystérieux", 67: "Naturel", 68: "Négliger", 69: "Normal", 70: "Objet",
    71: "Occupé", 72: "Étrange", 73: "Ouvert", 74: "Passage", 75: "Chemin",
    76: "Portail", 77: "Possessions", 78: "Silencieux", 79: "Rare", 80: "Rassurant",
    81: "Remarquable", 82: "Richesses", 83: "Chambre", 84: "Rugueux", 85: "Ruine",
    86: "Rustique", 87: "Effrayant", 88: "Simple", 89: "Petit", 90: "Malodorant",
    91: "Son", 92: "Escaliers", 93: "Maçonnerie", 94: "Technologie", 95: "Piège",
    96: "Trésor", 97: "Non naturel", 98: "Précieux", 99: "Chaud", 100: "Aqueux"
}


PIÈGES_DONJON = {
    1: "Agressif", 2: "Alliés", 3: "Embuscade", 4: "Animaux", 5: "Animer",
    6: "Antagoniser", 7: "Aromatique", 8: "Art", 9: "Attacher", 10: "Attention",
    11: "Attirer", 12: "Équilibre", 13: "Beau", 14: "Conférer", 15: "Trahir",
    16: "Bizarre", 17: "Lames", 18: "Casser", 19: "Plafond", 20: "Changer",
    21: "Choix", 22: "Grimper", 23: "Nuage", 24: "Froid", 25: "Coloré",
    26: "Combatif", 27: "Communiquer", 28: "Confondre", 29: "Contraindre", 30: "Contrôler",
    31: "Créer", 32: "Effrayant", 33: "Écraser", 34: "Endommagé", 35: "Danger",
    36: "Sombre", 37: "Tromper", 38: "Retarder", 39: "Priver", 40: "Perturber",
    41: "Diviser", 42: "Porte", 43: "Laisser tomber", 44: "Dupliquer", 45: "Élaborer",
    46: "Ennemis", 47: "Énergie", 48: "Tomber", 49: "Peur", 50: "Combattre",
    51: "Feu", 52: "Sol", 53: "Effrayant", 54: "Nuire", 55: "Chaleur",
    56: "Lourd", 57: "Impuissant", 58: "Horrible", 59: "Illusion", 60: "Emprisonner",
    61: "Létal", 62: "Bruyant", 63: "Leurre", 64: "Magie", 65: "Mécanique",
    66: "Mental", 67: "Désordonné", 68: "Monstre", 69: "Naturel", 70: "Objet",
    71: "Étrange", 72: "Vieux", 73: "Douleur", 74: "Plantes", 75: "Portail",
    76: "Possessions", 77: "Prison", 78: "Projectile", 79: "Énigme", 80: "Effrayant",
    81: "Simple", 82: "Sons", 83: "Poignarder", 84: "Arrêter", 85: "Étrange",
    86: "Étrangler", 87: "Supprimer", 88: "Prendre", 89: "Toxine", 90: "Transformer",
    91: "Transporter", 92: "Trésor", 93: "Épreuves", 94: "Déclencher", 95: "Libérer",
    96: "Mur", 97: "Avertissement", 98: "Eau", 99: "Arme", 100: "Blessure"
}


DESCRIPTEURS_FORÊT = {
    1: "Adversité", 2: "Agressif", 3: "Embuscade", 4: "Ancien", 5: "Animal",
    6: "Aromatique", 7: "Art", 8: "Assister", 9: "Moyen", 10: "Beau",
    11: "Bizarre", 12: "Sombre", 13: "Bloquer", 14: "Rocher", 15: "Grotte",
    16: "Chaotique", 17: "Falaise", 18: "Froid", 19: "Coloré", 20: "Combatif",
    21: "Communiquer", 22: "Effrayant", 23: "Endommagé", 24: "Danger", 25: "Sombre",
    26: "Mort", 27: "Délicat", 28: "Sec", 29: "", 30: "Rencontre",
    31: "Énorme", 32: "Environnement", 33: "Craintif", 34: "Faible", 35: "Féroce",
    36: "Nourriture", 37: "Chanceux", 38: "Frais", 39: "Rude", 40: "Sain",
    41: "Utile", 42: "Important", 43: "Information", 44: "Intense", 45: "Intéressant",
    46: "Manquant", 47: "Lac", 48: "Grand", 49: "Maigre", 50: "Rebord",
    51: "Létal", 52: "Bruyant", 53: "Magnifique", 54: "Majestueux", 55: "Masses",
    56: "Mature", 57: "Message", 58: "Puissant", 59: "Mundane", 60: "Mystérieux",
    61: "Naturel", 62: "Nature", 63: "Indescriptible", 64: "Normal", 65: "Étrange",
    66: "Vieux", 67: "Chemin", 68: "Paisible", 69: "Plantes", 70: "Étang",
    71: "Possessions", 72: "Puissant", 73: "Poursuivre", 74: "Silencieux", 75: "Rare",
    76: "Rassurant", 77: "Remarquable", 78: "Rivière", 79: "Roches", 80: "Rugueux",
    81: "Ruine", 82: "Effrayant", 83: "Simple", 84: "Pente", 85: "Petit",
    86: "Sons", 87: "Étrange", 88: "Fort", 89: "Menace", 90: "Tranquille",
    91: "Arbre", 92: "Inhabituel", 93: "Précieux", 94: "Violent", 95: "Chaud",
    96: "Aqueux", 97: "Faible", 98: "Temps", 99: "Sauvage", 100: "Jeune"
}


DIEUX = {
    1: "Actif", 2: "Alien", 3: "Ancien", 4: "Angélique", 5: "En colère",
    6: "Animal", 7: "Art", 8: "Assister", 9: "Attirer", 10: "Beau",
    11: "Conférer", 12: "Trahir", 13: "Bizarre", 14: "Capricieux", 15: "Coloré",
    16: "Combat", 17: "Communiquer", 18: "Conflit", 19: "Contrôler", 20: "Corruption",
    21: "Cosmique", 22: "Créer", 23: "Effrayant", 24: "Cruel", 25: "Culte",
    26: "Dangereux", 27: "Sombre", 28: "Mort", 29: "Tromperie", 30: "Destructeur",
    31: "Dégoûtant", 32: "Dominer", 33: "Rêves", 34: "", 35: "Émotions",
    36: "Ennemis", 37: "Énergie", 38: "Énorme", 39: "Mal", 40: "Féminin",
    41: "Déchu", 42: "Peur", 43: "Fertilité", 44: "Festif", 45: "Feu",
    46: "Effrayant", 47: "Généreux", 48: "Doux", 49: "Cadeaux", 50: "Glorieux",
    51: "Bon", 52: "Guide", 53: "Nuire", 54: "Rude", 55: "Guérir",
    56: "Humanoïde", 57: "Maladie", 58: "Emprisonner", 59: "Augmenter", 60: "Jaloux",
    61: "Justice", 62: "Connaissance", 63: "Liberté", 64: "Vie", 65: "Lumière",
    66: "Amour", 67: "Magie", 68: "Majestueux", 69: "Majeur", 70: "Malveillance",
    71: "Masculin", 72: "Puissant", 73: "Militaire", 74: "Mineur", 75: "Monstrueux",
    76: "Mundane", 77: "Mystérieux", 78: "Nature", 79: "Nuit", 80: "Opprimer",
    81: "Plaisirs", 82: "Pouvoir", 83: "Protecteur", 84: "Punir", 85: "Dirigeant",
    86: "Sacrifice", 87: "Étrange", 88: "Fort", 89: "Supprimer", 90: "Menace",
    91: "Transformer", 92: "Enfer", 93: "Violent", 94: "Guerre", 95: "Chaud",
    96: "Eau", 97: "Faible", 98: "Arme", 99: "Temps", 100: "Adoré"
}


LÉGENDES = {
    1: "Abandonner", 2: "Alliés", 3: "Colère", 4: "Assister", 5: "Accomplissement",
    6: "Se lier d'amitié", 7: "Conférer", 8: "Trahir", 9: "Bizarre", 10: "Bloquer",
    11: "Courageux", 12: "Casser", 13: "Fardeau", 14: "Négligence", 15: "Cataclysme",
    16: "Prudence", 17: "Changer", 18: "Conflit", 19: "Contrôler", 20: "Créer",
    21: "Crise", 22: "Endommager", 23: "Danger", 24: "Tromper", 25: "Diminuer",
    26: "Vaincu", 27: "Défiant", 28: "Retarder", 29: "Perturber", 30: "Diviser",
    31: "", 32: "Fin", 33: "Ennemis", 34: "Énergie", 35: "Mal",
    36: "Exposer", 37: "Échec", 38: "Renommée", 39: "Peur", 40: "Combattre",
    41: "Trouver", 42: "Libre", 43: "Amitié", 44: "Effrayant", 45: "Bon",
    46: "Guide", 47: "Nuire", 48: "Guérir", 49: "Aider", 50: "Impuissant",
    51: "Héros", 52: "Caché", 53: "Historique", 54: "Maladie", 55: "Important",
    56: "Emprisonner", 57: "Augmenter", 58: "Informer", 59: "Innocent", 60: "Intrigue",
    61: "Jalousie", 62: "Juge", 63: "Leadership", 64: "Légal", 65: "Létal",
    66: "Liberté", 67: "Perte", 68: "Amour", 69: "Loyauté", 70: "Masses",
    71: "Puissant", 72: "Militaire", 73: "Malchance", 74: "Monstre", 75: "Bouger",
    76: "Mundane", 77: "Mystérieux", 78: "Naturel", 79: "Vieux", 80: "S'opposer",
    81: "Opprimer", 82: "Paix", 83: "Complot", 84: "Possessions", 85: "Pouvoir",
    86: "Punir", 87: "Poursuivre", 88: "Libérer", 89: "Retour", 90: "Richesses",
    91: "Ruine", 92: "Sauveur", 93: "Arrêter", 94: "Étrange", 95: "Lutte",
    96: "Vol", 97: "Confiance", 98: "Usurper", 99: "Vengeance", 100: "Méchant"
}


EMPLACEMENTS = {
    1: "Abandonné", 2: "Actif", 3: "Artistique", 4: "Atmosphère", 5: "Beau",
    6: "Sombre", 7: "Brillant", 8: "Affaires", 9: "Calme", 10: "Charmant",
    11: "Propre", 12: "Encombré", 13: "Froid", 14: "Coloré", 15: "Incolore",
    16: "Confus", 17: "Exigu", 18: "Effrayant", 19: "Brut", 20: "Mignon",
    21: "Endommagé", 22: "Dangereux", 23: "Sombre", 24: "Délicieux", 25: "Sale",
    26: "Domestique", 27: "Vide", 28: "Enfermé", 29: "Énorme", 30: "Entrée",
    31: "Exclusif", 32: "Exposé", 33: "Extravagant", 34: "Familier", 35: "Fantaisie",
    36: "Festif", 37: "Présage", 38: "Chanceux", 39: "Parfumé", 40: "Frénétique",
    41: "Effrayant", 42: "Plein", 43: "Nuisible", 44: "Utile", 45: "Horrible",
    46: "Important", 47: "Impressionnant", 48: "Inactif", 49: "Intense", 50: "Intrigant",
    51: "Vivant", 52: "Solitaire", 53: "Long", 54: "Bruyant", 55: "Significatif",
    56: "Désordonné", 57: "Mobile", 58: "Moderne", 59: "Mundane", 60: "Mystérieux",
    61: "Naturel", 62: "Nouveau", 63: "Occupé", 64: "Étrange", 65: "Officiel",
    66: "Vieux", 67: "Ouvert", 68: "Paisible", 69: "Personnel", 70: "Simple",
    71: "Portail", 72: "Protégé", 73: "Protection", 74: "Intentionnel", 75: "Silencieux",
    76: "Rassurant", 77: "Éloigné", 78: "Ingénieux", 79: "Ruine", 80: "Rustique",
    81: "Sûr", 82: "Services", 83: "Simple", 84: "Petit", 85: "Spacieux",
    86: "Stockage", 87: "Étrange", 88: "Stylé", 89: "Suspicieux", 90: "Grand",
    91: "Menace", 92: "Tranquille", 93: "Inattendu", 94: "Désagréable", 95: "Inhabituel",
    96: "Utile", 97: "Chaud", 98: "Avertissement", 99: "Aqueux", 100: "Accueillant"
}


DESCRIPTEURS_OBJET_MAGIQUE = {
    1: "Animal", 2: "Animer", 3: "Zone", 4: "Armure", 5: "Assister",
    6: "Attaquer", 7: "Attirer", 8: "Bénéfice", 9: "Conférer", 10: "Bloquer",
    11: "Livre", 12: "Changer", 13: "Vêtements", 14: "Nuage", 15: "Froid",
    16: "Communication", 17: "Conteneur", 18: "Contrôler", 19: "Créer", 20: "Malédiction",
    21: "Endommager", 22: "Mort", 23: "Tromperie", 24: "Diminuer", 25: "Défense",
    26: "Détruire", 27: "Détecter", 28: "Dimensions", 29: "", 30: "Émotion",
    31: "Énergie", 32: "Améliorer", 33: "Environnement", 34: "Échapper", 35: "Mal",
    36: "Exploser", 37: "Peur", 38: "Feu", 39: "Vol", 40: "Nourriture",
    41: "Gemme", 42: "Bon", 43: "Groupe", 44: "Nuire", 45: "Guérir",
    46: "Santé", 47: "Utile", 48: "Maladie", 49: "Illusion", 50: "Imprégner",
    51: "Imiter", 52: "Augmenter", 53: "Information", 54: "Inhiber", 55: "Instantané",
    56: "Bijoux", 57: "Létal", 58: "Vie", 59: "Lumière", 60: "Limité",
    61: "Liquide", 62: "Mental", 63: "Monstre", 64: "Multi", 65: "Nature",
    66: "Objet", 67: "Orbe", 68: "Autres", 69: "Physique", 70: "Plantes",
    71: "Poison", 72: "Potion", 73: "Pouvoir", 74: "À distance", 75: "Résistance",
    76: "Restaurer", 77: "Anneau", 78: "Corde", 79: "Rune", 80: "Sécurité",
    81: "Parchemin", 82: "Soi", 83: "Sens", 84: "Compétence", 85: "Spécial",
    86: "Vitesse", 87: "Sort", 88: "Bâton", 89: "Étrange", 90: "Invoquer",
    91: "Épée", 92: "Outil", 93: "Transformer", 94: "Piège", 95: "Voyager",
    96: "Utile", 97: "Utilitaire", 98: "Baguette", 99: "Eau", 100: "Arme"
}


DESCRIPTEURS_MUTATION = {
    1: "Agilité", 2: "Animal", 3: "Apparence", 4: "Armure", 5: "Assister",
    6: "Attacher", 7: "Attaquer", 8: "Bénéfice", 9: "Conférer", 10: "Bizarre",
    11: "Bloquer", 12: "Corps", 13: "Changer", 14: "Griffes", 15: "Couleur",
    16: "Combat", 17: "Communiquer", 18: "Cacher", 19: "Contraindre", 20: "Contrôler",
    21: "Créer", 22: "Endommager", 23: "Tromper", 24: "Diminuer", 25: "Défaut",
    26: "Défense", 27: "Déformé", 28: "Détecter", 29: "Diminuer", 30: "Perturber",
    31: "Dominer", 32: "", 33: "Énergie", 34: "Améliorer", 35: "Environnement",
    36: "Exposer", 37: "Extra", 38: "Yeux", 39: "Peur", 40: "Combattre",
    41: "Voler", 42: "Libre", 43: "Nuire", 44: "Guérir", 45: "Santé",
    46: "Chaleur", 47: "Utile", 48: "Horrible", 49: "Imiter", 50: "Immunité",
    51: "Emprisonner", 52: "Augmenter", 53: "Information", 54: "Inspecter", 55: "Grand",
    56: "Apprendre", 57: "Létal", 58: "Membre", 59: "Limiter", 60: "Mental",
    61: "Désordonné", 62: "Bouger", 63: "Nature", 64: "Douleur", 65: "Partiel",
    66: "Pouvoir", 67: "Projectile", 68: "Protection", 69: "À distance", 70: "Recharger",
    71: "Libérer", 72: "Remplacer", 73: "Exigence", 74: "Résistance", 75: "Restaurer",
    76: "Révéler", 77: "Effrayant", 78: "Sens", 79: "Simple", 80: "Compétence",
    81: "Arrêter", 82: "Étrange", 83: "Force", 84: "Fort", 85: "Lutte",
    86: "Souffrir", 87: "Supprimer", 88: "Environnement", 89: "Survivre", 90: "Nager",
    91: "Toxique", 92: "Transformer", 93: "Voyager", 94: "Usurper", 95: "Violence",
    96: "Vulnérabilité", 97: "Chaud", 98: "Faible", 99: "Arme", 100: "Blessure"
}


NOMS = {
    1: "A", 2: "Action", 3: "Ah", 4: "Ahg", 5: "An",
    6: "Animal", 7: "Ar", 8: "As", 9: "B", 10: "Bah",
    11: "Be", 12: "Bih", 13: "Brah", 14: "Col", 15: "Couleur",
    16: "Cor", 17: "Dah", 18: "Actes", 19: "Del", 20: "Drah",
    21: "Eee", 22: "Eh", 23: "Ei", 24: "Ell", 25: "",
    26: "Émotion", 27: "Ess", 28: "Est", 29: "Et", 30: "Fah",
    31: "Fer", 32: "Fi", 33: "Floral", 34: "Gah", 35: "Go",
    36: "Grah", 37: "Hee", 38: "Ia", 39: "Ick", 40: "In",
    41: "Iss", 42: "Je", 43: "Ke", 44: "Jen", 45: "Kha",
    46: "Kr", 47: "Lah", 48: "Lee", 49: "Len", 50: "Lin",
    51: "Emplacement", 52: "Ly", 53: "Mah", 54: "Militaire", 55: "Méfait",
    56: "N", 57: "Nah", 58: "Nature", 59: "Nee", 60: "Nn",
    61: "Nombre", 62: "Occupation", 63: "Oh", 64: "On", 65: "Or",
    66: "Orn", 67: "Oth", 68: "Ow", 69: "Ph", 70: "Pr",
    71: "R", 72: "Rah", 73: "Ren", 74: "Sah", 75: "Se",
    76: "Sh", 77: "Sha", 78: "T", 79: "Ta", 80: "Tal",
    81: "Tar", 82: "Th", 83: "Thah", 84: "Thoh", 85: "Ti",
    86: "Temps", 87: "Tor", 88: "Uh", 89: "Va", 90: "Vah",
    91: "Ve", 92: "Vice", 93: "Vertu", 94: "Wah", 95: "Wr",
    96: "X", 97: "Y", 98: "Yah", 99: "Yuh", 100: "Z"
}


MAISON_NOBLE = {
    1: "Agressif", 2: "Alliés", 3: "Colère", 4: "Conférer", 5: "Trahir",
    6: "Bizarre", 7: "Bloquer", 8: "Casser", 9: "Bureaucratie", 10: "Prudent",
    11: "Changer", 12: "Commerce", 13: "Compromis", 14: "Conflit", 15: "Connexions",
    16: "Contrôler", 17: "Créer", 18: "Crise", 19: "Cruel", 20: "Dangereux",
    21: "Mort", 22: "Tromperie", 23: "Défaite", 24: "Défiant", 25: "Perturber",
    26: "Ennemis", 27: "Extravagant", 28: "Fané", 29: "Renommée", 30: "Famille",
    31: "Quartier général", 32: "Héritage", 33: "Héros", 34: "Histoire", 35: "Maison",
    36: "Important", 37: "Emprisonner", 38: "Augmenter", 39: "Information", 40: "Intrigue",
    41: "Investissement", 42: "Terre", 43: "Grand", 44: "Leadership", 45: "Légal",
    46: "Levier", 47: "Liberté", 48: "Amour", 49: "Loyal", 50: "Magnifique",
    51: "Malveillance", 52: "Puissant", 53: "Militaire", 54: "Malchance", 55: "Bouger",
    56: "Mystérieux", 57: "Négliger", 58: "Vieux", 59: "S'opposer", 60: "Opprimer",
    61: "Renverser", 62: "Passion", 63: "Paix", 64: "Persécuter", 65: "Plans",
    66: "Politique", 67: "Possessions", 68: "Puissant", 69: "Public", 70: "Refuser",
    71: "Libérer", 72: "Remarquable", 73: "Retour", 74: "Richesses", 75: "Royauté",
    76: "Impitoyable", 77: "Secret", 78: "Sécurité", 79: "Serviteur", 80: "Espion",
    81: "Étrange", 82: "Fort", 83: "Lutte", 84: "Succession", 85: "Souffrance",
    86: "Supprimer", 87: "Tactiques", 88: "Tension", 89: "Voyager", 90: "Confiance",
    91: "Usurper", 92: "Précieux", 93: "Vengeance", 94: "Victoire", 95: "Violence",
    96: "Guerre", 97: "Faible", 98: "Richesse", 99: "Arme", 100: "Jeune"
}


OBJETS = {
    1: "Actif", 2: "Artistique", 3: "Moyen", 4: "Beau", 5: "Bizarre",
    6: "Brillant", 7: "Vêtements", 8: "Indice", 9: "Froid", 10: "Coloré",
    11: "Communication", 12: "Compliqué", 13: "Confus", 14: "Consommable", 15: "Conteneur",
    16: "Effrayant", 17: "Brut", 18: "Mignon", 19: "Endommagé", 20: "Dangereux",
    21: "Désactivé", 22: "Délibéré", 23: "Délicieux", 24: "Désiré", 25: "Domestique",
    26: "Vide", 27: "Énergie", 28: "Énorme", 29: "Équipement", 30: "Attendu",
    31: "Épuisé", 32: "Extravagant", 33: "Fané", 34: "Familier", 35: "Fantaisie",
    36: "Flore", 37: "Chanceux", 38: "Fragile", 39: "Parfumé", 40: "Effrayant",
    41: "Ordures", 42: "Orientation", 43: "Dur", 44: "Nuisible", 45: "Guérison",
    46: "Lourd", 47: "Utile", 48: "Horrible", 49: "Important", 50: "Inactif",
    51: "Information", 52: "Intrigant", 53: "Grand", 54: "Létal", 55: "Lumière",
    56: "Liquide", 57: "Bruyant", 58: "Majestueux", 59: "Significatif", 60: "Mécanique",
    61: "Moderne", 62: "En mouvement", 63: "Multiple", 64: "Mundane", 65: "Mystérieux",
    66: "Naturel", 67: "Nouveau", 68: "Étrange", 69: "Officiel", 70: "Vieux",
    71: "Ornemental", 72: "Orné", 73: "Personnel", 74: "Puissant", 75: "Prisé",
    76: "Protection", 77: "Rare", 78: "Prêt", 79: "Rassurant", 80: "Ressource",
    81: "Ruine", 82: "Petit", 83: "Doux", 84: "Solitaire", 85: "Volé",
    86: "Étrange", 87: "Stylé", 88: "Menace", 89: "Outil", 90: "Voyager",
    91: "Inattendu", 92: "Désagréable", 93: "Inhabituel", 94: "Utile", 95: "Inutile",
    96: "Précieux", 97: "Chaud", 98: "Arme", 99: "Mouillé", 100: "Usé"
}


REBONDISSEMENTS = {
    1: "Action", 2: "Attaquer", 3: "Mauvais", 4: "Barrière", 5: "Trahir",
    6: "Affaires", 7: "Changer", 8: "Personnage", 9: "Conclure", 10: "Conditionnel",
    11: "Conflit", 12: "Connexion", 13: "Conséquence", 14: "Contrôler", 15: "Danger",
    16: "Mort", 17: "Retarder", 18: "Détruire", 19: "Diminuer", 20: "Désastre",
    21: "Découvrir", 22: "Émotion", 23: "Ennemi", 24: "Améliorer", 25: "Entrer",
    26: "Échapper", 27: "Preuve", 28: "Échec", 29: "Famille", 30: "Libre",
    31: "Ami", 32: "Bon", 33: "Groupe", 34: "Nuire", 35: "Quartier général",
    36: "Aider", 37: "Impuissant", 38: "Caché", 39: "Idée", 40: "Immédiat",
    41: "Imminent", 42: "Important", 43: "Incapaciter", 44: "Information", 45: "Injustice",
    46: "Leader", 47: "Légal", 48: "Létal", 49: "Mensonge", 50: "Limiter",
    51: "Emplacement", 52: "Chanceux", 53: "Mental", 54: "Manquant", 55: "Mundane",
    56: "Mystère", 57: "Nécessaire", 58: "Nouvelles", 59: "Objet", 60: "S'opposer",
    61: "Paria", 62: "Surmonter", 63: "Passé", 64: "Paix", 65: "Personnel",
    66: "Persuader", 67: "Physique", 68: "Plan", 69: "Pouvoir", 70: "Préparer",
    71: "Problème", 72: "Promesse", 73: "Protéger", 74: "Public", 75: "Poursuivre",
    76: "Rare", 77: "Éloigné", 78: "Réparer", 79: "Répéter", 80: "Exiger",
    81: "Sauver", 82: "Ressource", 83: "Réponse", 84: "Révéler", 85: "Vengeance",
    86: "Renversement", 87: "Récompense", 88: "Compétence", 89: "Social", 90: "Solution",
    91: "Étrange", 92: "Succès", 93: "Tension", 94: "Piège", 95: "Voyager",
    96: "Inconnu", 97: "Improbable", 98: "Inhabituel", 99: "Urgent", 100: "Utile"
}


POUVOIRS = {
    1: "Absorber", 2: "Adversité", 3: "Altérer", 4: "Animer", 5: "Assister",
    6: "Attacher", 7: "Attaquer", 8: "Bloquer", 9: "Corps", 10: "Changer",
    11: "Chimique", 12: "Froid", 13: "Coloré", 14: "Combat", 15: "Combiner",
    16: "Communiquer", 17: "Contrôler", 18: "Cosmétique", 19: "Créer", 20: "Créature",
    21: "Endommager", 22: "Sombre", 23: "Mort", 24: "Tromper", 25: "Défense",
    26: "Retarder", 27: "Détruire", 28: "Détecter", 29: "Dimensions", 30: "Diminuer",
    31: "Perturber", 32: "Distance", 33: "Dominer", 34: "Dupliquer", 35: "Électricité",
    36: "", 37: "Émission", 38: "Émotion", 39: "Ennemis", 40: "Énergie",
    41: "Améliorer", 42: "Environnement", 43: "Explosion", 44: "Extra", 45: "Feu",
    46: "Vol", 47: "Libre", 48: "Ami", 49: "Nuire", 50: "Guérir",
    51: "Chaleur", 52: "Aider", 53: "Cacher", 54: "Illusion", 55: "Imprégner",
    56: "Immunité", 57: "Augmenter", 58: "Information", 59: "Vie", 60: "Lumière",
    61: "Membre", 62: "Limité", 63: "Emplacement", 64: "Magie", 65: "Majeur",
    66: "Manipuler", 67: "Matière", 68: "Mental", 69: "Mineur", 70: "Naturel",
    71: "Nature", 72: "Objet", 73: "Autres", 74: "Physique", 75: "Plantes",
    76: "Poison", 77: "Pouvoir", 78: "Protéger", 79: "Rayon", 80: "À distance",
    81: "Réfléchir", 82: "Repousser", 83: "Résistance", 84: "Révéler", 85: "Soi",
    86: "Sens", 87: "Compétence", 88: "Esprit", 89: "Furtivité", 90: "Étrange",
    91: "Invoquer", 92: "Changer", 93: "Prendre", 94: "Technologie", 95: "Temps",
    96: "Transformer", 97: "Piège", 98: "Voyager", 99: "Arme", 100: "Temps"
}


RÉSULTATS_FOUILLE = {
    1: "Abondance", 2: "Activité", 3: "Adversité", 4: "Alliés", 5: "Animal",
    6: "Art", 7: "Barrière", 8: "Beauté", 9: "Bizarre", 10: "Sombre",
    11: "Cassé", 12: "Propre", 13: "Vêtements", 14: "Confort", 15: "Communiquer",
    16: "Compétition", 17: "Dissimulation", 18: "Conflit", 19: "Conteneur", 20: "Contrôler",
    21: "Crise", 22: "Endommagé", 23: "Danger", 24: "Mort", 25: "Sale",
    26: "Désagréable", 27: "Dégoûtant", 28: "Dispute", 29: "Boisson", 30: "",
    31: "Vide", 32: "Ennemis", 33: "Énergie", 34: "Extravagance", 35: "Échec",
    36: "Peur", 37: "Combattre", 38: "Nourriture", 39: "Frais", 40: "Amitié",
    41: "Carburant", 42: "Bon", 43: "Santé", 44: "Utile", 45: "Espoir",
    46: "Important", 47: "Information", 48: "Joie", 49: "Grand", 50: "Somptueux",
    51: "Maigre", 52: "Moins", 53: "Létal", 54: "Mécanique", 55: "Médicinal",
    56: "Désordonné", 57: "Malchance", 58: "Mundane", 59: "Mystérieux", 60: "Nature",
    61: "Nouveau", 62: "Normal", 63: "Étrange", 64: "Officiel", 65: "Vieux",
    66: "Ouvert", 67: "Opposition", 68: "Douleur", 69: "Paix", 70: "Plaisirs",
    71: "Portail", 72: "Possessions", 73: "Protection", 74: "Rassurant", 75: "Réparable",
    76: "Pourri", 77: "Rugueux", 78: "Ruine", 79: "Effrayant", 80: "Abri",
    81: "Simple", 82: "Petit", 83: "Malodorant", 84: "Étrange", 85: "Lutte",
    86: "Succès", 87: "Approvisionnement", 88: "Technologie", 89: "Outil", 90: "Voyager",
    91: "Triomphe", 92: "Problème", 93: "Inutile", 94: "Précieux", 95: "Véhicule",
    96: "Victoire", 97: "Violence", 98: "Chaud", 99: "Déchet", 100: "Arme"
}


ODEURS = {
    1: "Acre", 2: "Animal", 3: "Antiseptique", 4: "Aromatique", 5: "Artificiel",
    6: "Attrayant", 7: "Mauvais", 8: "Bizarre", 9: "Brûlé", 10: "Chimique",
    11: "Propre", 12: "Réconfortant", 13: "Cuisine", 14: "Décrépit", 15: "Délicieux",
    16: "Délicieux", 17: "Sale", 18: "Désagréable", 19: "Dégoûtant", 20: "Sec",
    21: "Ennuyant", 22: "Terreux", 23: "Électrique", 24: "Évocateur", 25: "Fané",
    26: "Faible", 27: "Familier", 28: "Fétide", 29: "Poisson", 30: "Floral",
    31: "Nourriture", 32: "Fétide", 33: "Parfumé", 34: "Frais", 35: "Fruité",
    36: "Funky", 37: "Bon", 38: "Herbeux", 39: "Gratifiant", 40: "Enivrant",
    41: "Lourd", 42: "Herbal", 43: "Horrible", 44: "Humide", 45: "Industriel",
    46: "Intéressant", 47: "Enivrant", 48: "Irritant", 49: "Manquant", 50: "Chargé",
    51: "Malodorant", 52: "Significatif", 53: "Médicinal", 54: "Métallique", 55: "Moisi",
    56: "Humide", 57: "Mousseux", 58: "Musqué", 59: "Moisi", 60: "Mystérieux",
    61: "Naturel", 62: "Nature", 63: "Nauséabond", 64: "Normal", 65: "Étrange",
    66: "Inodore", 67: "Offensif", 68: "Accablant", 69: "Parfumé", 70: "Plaisant",
    71: "Puissant", 72: "Piquant", 73: "Punitif", 74: "Putride", 75: "Rance",
    76: "Rassurant", 77: "Puanteur", 78: "Riche", 79: "Mûr", 80: "Pourriture",
    81: "Pourri", 82: "Savoureux", 83: "Malodorant", 84: "Fumé", 85: "Aigre",
    86: "Stagnant", 87: "Rassis", 88: "Puanteur", 89: "Piquant", 90: "Étrange",
    91: "Fort", 92: "Étouffant", 93: "Sulfurique", 94: "Doux", 95: "Chaud",
    96: "Déchet", 97: "Aqueux", 98: "Faible", 99: "Temps", 100: "Boisé"
}


SONS = {
    1: "Activité", 2: "Alarme", 3: "Animal", 4: "Approche", 5: "Cognement",
    6: "Bataille", 7: "Bip", 8: "Cloche", 9: "Imploration", 10: "Bizarre",
    11: "Brûlure", 12: "Occupé", 13: "Calme", 14: "Incessant", 15: "Célébrer",
    16: "Chaotique", 17: "Joyeux", 18: "Clang", 19: "Combattif", 20: "Communiquer",
    21: "Construction", 22: "Conversation", 23: "Crash", 24: "Grincement", 25: "Effrayant",
    26: "Pleurs", 27: "Dommages", 28: "Danger", 29: "Désagréable", 30: "Lointain",
    31: "Goutte", 32: "Écho", 33: "Émotion", 34: "Énergique", 35: "Explosion",
    36: "Familier", 37: "Féroce", 38: "Pas", 39: "Frénétique", 40: "Effrayant",
    41: "Broyage", 42: "Grogner", 43: "Martèlement", 44: "Utile", 45: "Imiter",
    46: "Important", 47: "Indistinct", 48: "Industrie", 49: "Information", 50: "Innocent",
    51: "Intense", 52: "Intéressant", 53: "Irritant", 54: "Fort", 55: "Machinerie",
    56: "Significatif", 57: "Métallique", 58: "Assourdi", 59: "Multiple", 60: "Musique",
    61: "Mystérieux", 62: "Naturel", 63: "Proche", 64: "Bruyant", 65: "Normal",
    66: "Étrange", 67: "Productivité", 68: "Poursuite", 69: "Silencieux", 70: "Rassurant",
    71: "Remarquable", 72: "Déchirure", 73: "Rugissement", 74: "Grondement", 75: "Frottement",
    76: "Effrayant", 77: "Grattage", 78: "Éraflure", 79: "Simple", 80: "Grésillement",
    81: "Claquement", 82: "Lent", 83: "Doux", 84: "Commencer", 85: "Arrêter",
    86: "Étrange", 87: "Tapotement", 88: "Technologie", 89: "Menaçant", 90: "Bruissement",
    91: "Trafic", 92: "Tranquille", 93: "Incertain", 94: "Avertissement", 95: "Eau",
    96: "Météo", 97: "Vrombissement", 98: "Sifflement", 99: "Sauvage", 100: "Vent"
}


EFFETS_SORTS = {
    1: "Animal", 2: "Animer", 3: "Assister", 4: "Attaquer", 5: "Attirer",
    6: "Conférer", 7: "Bizarre", 8: "Bloquer", 9: "Casser", 10: "Brillant",
    11: "Brûler", 12: "Changer", 13: "Nuage", 14: "Froid", 15: "Communiquer",
    16: "Cacher", 17: "Convoquer", 18: "Contrôler", 19: "Contrecarrer", 20: "Créer",
    21: "Créature", 22: "Malédiction", 23: "Dommages", 24: "Sombre", 25: "Mort",
    26: "Tromper", 27: "Diminuer", 28: "Défense", 29: "Détruire", 30: "Détecter",
    31: "Diminuer", 32: "Maladie", 33: "Dominer", 34: "Dupliquer", 35: "Terre",
    36: "", 37: "Émotion", 38: "Ennemis", 39: "Énergie", 40: "Améliorer",
    41: "Environnement", 42: "Exposer", 43: "Feu", 44: "Réparer", 45: "Nourriture",
    46: "Libérer", 47: "Groupe", 48: "Guider", 49: "Entraver", 50: "Nuire",
    51: "Guérir", 52: "Utile", 53: "Glace", 54: "Illusion", 55: "Imprégner",
    56: "Immunité", 57: "Emprisonner", 58: "Information", 59: "Inspecter", 60: "Vie",
    61: "Lumière", 62: "Limitation", 63: "Liquide", 64: "Fort", 65: "Manipulation",
    66: "Esprit", 67: "Nature", 68: "Objet", 69: "Autres", 70: "Douleur",
    71: "Physique", 72: "Plante", 73: "Poison", 74: "Portail", 75: "Puissant",
    76: "Protéger", 77: "Rayon", 78: "À distance", 79: "Résistance", 80: "Restaurer",
    81: "Soi", 82: "Sens", 83: "Bouclier", 84: "Âme", 85: "Étrange",
    86: "Force", 87: "Étourdir", 88: "Invoquer", 89: "Temps", 90: "Transformer",
    91: "Piège", 92: "Voyager", 93: "Déclencher", 94: "Incertain", 95: "Mort-vivant",
    96: "Mur", 97: "Eau", 98: "Faible", 99: "Arme", 100: "Météo"
}


DESCRIPTEURS_VAISSEAU = {
    1: "Activité", 2: "Adversité", 3: "Assister", 4: "Automatisé", 5: "Bataille",
    6: "Beau", 7: "Conférer", 8: "Sombre", 9: "Bloquer", 10: "Brillant",
    11: "Affaires", 12: "Propre", 13: "Froid", 14: "Coloré", 15: "Combattif",
    16: "Communiquer", 17: "Ordinateur", 18: "Contenir", 19: "Contrôler", 20: "Effrayant",
    21: "Équipage", 22: "Endommagé", 23: "Danger", 24: "Sombre", 25: "Mort",
    26: "Défense", 27: "Élaboré", 28: "Vide", 29: "Énergie", 30: "Moteur",
    31: "Énorme", 32: "Environnement", 33: "Évasion", 34: "Sortie", 35: "Extérieur",
    36: "Peur", 37: "Nourriture", 38: "Plein", 39: "Salle", 40: "Santé",
    41: "Utile", 42: "Important", 43: "Information", 44: "Enquêter", 45: "Intéressant",
    46: "Manquant", 47: "Grand", 48: "Somptueux", 49: "Létal", 50: "Fort",
    51: "Magnifique", 52: "Entretien", 53: "Significatif", 54: "Mécanique", 55: "Message",
    56: "Désordonné", 57: "Puissant", 58: "Militaire", 59: "Moderne", 60: "Multiple",
    61: "Mundane", 62: "Mystérieux", 63: "Naturel", 64: "Normal", 65: "Étrange",
    66: "Portail", 67: "Possessions", 68: "Puissance", 69: "Puissant", 70: "Prison",
    71: "Protection", 72: "Silencieux", 73: "Rare", 74: "Rassurant", 75: "Remarquable",
    76: "Ressources", 77: "Chambre", 78: "Rugueux", 79: "Ruine", 80: "Effrayant",
    81: "Sécurité", 82: "Simple", 83: "Petit", 84: "Sons", 85: "Commencer",
    86: "Arrêter", 87: "Stockage", 88: "Étrange", 89: "Fournitures", 90: "Survie",
    91: "Système", 92: "Tactiques", 93: "Technologie", 94: "Voyager", 95: "Inhabituel",
    96: "Précieux", 97: "Véhicule", 98: "Chaud", 99: "Arme", 100: "Travail"
}


DESCRIPTEURS_TERRAIN = {
    1: "Abandonné", 2: "Abondant", 3: "Activité", 4: "Avancé", 5: "Alliés",
    6: "Ancien", 7: "Animaux", 8: "Atmosphère", 9: "Stérile", 10: "Beau",
    11: "Bizarre", 12: "Catastrophe", 13: "Chaotique", 14: "Ville", 15: "Civilisation",
    16: "Falaises", 17: "Nuages", 18: "Froid", 19: "Coloré", 20: "Combattif",
    21: "Communiquer", 22: "Conflit", 23: "Endommagé", 24: "Danger", 25: "Défense",
    26: "Désert", 27: "Sec", 28: "Terne", 29: "", 30: "Vide",
    31: "Énergie", 32: "Énorme", 33: "Environnement", 34: "Fertile", 35: "Effrayant",
    36: "Habitable", 37: "Rude", 38: "Brumeux", 39: "Sain", 40: "Utile",
    41: "Hostile", 42: "Chaud", 43: "Intense", 44: "Intéressant", 45: "Grand",
    46: "Létal", 47: "Vie", 48: "Charmant", 49: "Magnifique", 50: "Masses",
    51: "Mécanique", 52: "Message", 53: "Puissant", 54: "Malchance", 55: "Montagneux",
    56: "Multiple", 57: "Mundane", 58: "Mystérieux", 59: "Naturel", 60: "Nature",
    61: "Indescriptible", 62: "Océan", 63: "Étrange", 64: "Paisible", 65: "Personnes",
    66: "Plantes", 67: "Peuplé", 68: "Puissant", 69: "Primitif", 70: "Pluie",
    71: "Rare", 72: "Remarquable", 73: "Ingénieux", 74: "Richesses", 75: "Rivière",
    76: "Rocailleux", 77: "Rugueux", 78: "Ruine", 79: "Ruines", 80: "Sablonneux",
    81: "Effrayant", 82: "Simple", 83: "Petit", 84: "Étrange", 85: "Fort",
    86: "Technologie", 87: "Menaçant", 88: "Toxique", 89: "Tranquille", 90: "Arbres",
    91: "Inhabituel", 92: "Précieux", 93: "Violent", 94: "Chaud", 95: "Eau",
    96: "Faible", 97: "Météo", 98: "Sauvage", 99: "Venteux", 100: "Merveilles"
}


DESCRIPTEURS_MORTS_VIVANTS = {
    1: "Actif", 2: "Agressif", 3: "En colère", 4: "Animal", 5: "Anxieux",
    6: "Attirer", 7: "Beau", 8: "Conférer", 9: "Bizarre", 10: "Sombre",
    11: "Audacieux", 12: "Lié", 13: "Froid", 14: "Combattif", 15: "Communiquer",
    16: "Contrôler", 17: "Créer", 18: "Effrayant", 19: "Dangereux", 20: "Sombre",
    21: "Tromper", 22: "Sale", 23: "Dégoûtant", 24: "", 25: "Ennemis",
    26: "Énergie", 27: "Environnement", 28: "Mal", 29: "Rapide", 30: "Peur",
    31: "Combattre", 32: "Flottant", 33: "Amical", 34: "Effrayant", 35: "Content",
    36: "Lueur", 37: "Objectifs", 38: "Bon", 39: "Guider", 40: "Nuire",
    41: "Utile", 42: "Impuissant", 43: "Historique", 44: "Horrible", 45: "Affamé",
    46: "Imiter", 47: "Information", 48: "Insignifiant", 49: "Intelligent", 50: "Grand",
    51: "Leadership", 52: "Létal", 53: "Lumière", 54: "Limité", 55: "Solitaire",
    56: "Amour", 57: "Macabre", 58: "Malveillance", 59: "Message", 60: "Désordonné",
    61: "Puissant", 62: "Sans esprit", 63: "Misérable", 64: "Malchance", 65: "Monstrueux",
    66: "Mundane", 67: "Étrange", 68: "Vieux", 69: "Douleur", 70: "Pâle",
    71: "Passif", 72: "Possessions", 73: "Possessif", 74: "Puissant", 75: "Pouvoirs",
    76: "Délibéré", 77: "Poursuivre", 78: "Silencieux", 79: "Résistant", 80: "Pourrissant",
    81: "Effrayant", 82: "Cherchant", 83: "Traînant", 84: "Lent", 85: "Petit",
    86: "Malodorant", 87: "Étrange", 88: "Fort", 89: "Menaçant", 90: "Dur",
    91: "Transformer", 92: "Voyager", 93: "Tricher", 94: "Vengeur", 95: "Violent",
    96: "Faible", 97: "Faiblesse", 98: "Armes", 99: "Blessures", 100: "Jeune"
}


VISIONS_RÊVES = {
    1: "Activité", 2: "Adversité", 3: "Alliés", 4: "Assister", 5: "Accomplissement",
    6: "Bizarre", 7: "Sombre", 8: "Catastrophe", 9: "Célébrer", 10: "Changer",
    11: "Coloré", 12: "Conflit", 13: "Contact", 14: "Contrôler", 15: "Effrayant",
    16: "Crise", 17: "Cruauté", 18: "Danger", 19: "Sombre", 20: "Mort",
    21: "Défaite", 22: "Perturbation", 23: "", 24: "Émotions", 25: "Ennemis",
    26: "Énergie", 27: "Environnement", 28: "Événement", 29: "Mal", 30: "Échec",
    31: "Peur", 32: "Festif", 33: "Combattre", 34: "Amitié", 35: "Effrayant",
    36: "Futur", 37: "Objectifs", 38: "Bon", 39: "Orientation", 40: "Nuire",
    41: "Utile", 42: "Impuissant", 43: "Indice", 44: "Espoir", 45: "Horrible",
    46: "Hâte", 47: "Idées", 48: "Implorer", 49: "Important", 50: "Incomplet",
    51: "Information", 52: "Instruction", 53: "Liberté", 54: "Mensonges", 55: "Amour",
    56: "Malveillance", 57: "Masses", 58: "Mécanique", 59: "Message", 60: "Désordonné",
    61: "Militaire", 62: "Malchance", 63: "Mundane", 64: "Mystérieux", 65: "Naturel",
    66: "Obscur", 67: "Étrange", 68: "Opposer", 69: "Chemin", 70: "Paix",
    71: "Personnes", 72: "Lieu", 73: "Plans", 74: "Complot", 75: "Positif",
    76: "Possessions", 77: "Pouvoir", 78: "Évitable", 79: "Rassurant", 80: "Richesses",
    81: "Énigme", 82: "Ruine", 83: "Effrayant", 84: "Simple", 85: "Étrange",
    86: "Lutte", 87: "Succès", 88: "Souffrance", 89: "Supprimer", 90: "Tension",
    91: "Menace", 92: "Temps", 93: "Voyager", 94: "Problème", 95: "Confiance",
    96: "Incertain", 97: "Inquiétant", 98: "Violence", 99: "Avertissement", 100: "Arme"
}



@app.route("/roll_table", methods=["GET"])
def roll_table():
    table = request.args.get("table")
    if table == "scene_adjustment":
        roll = random.randint(1, 10)
        result = SCENE_ADJUSTMENT_TABLE.get(roll, "Inconnu")
        return jsonify({"roll": roll, "result": result})
    elif table == "random_event_focus":
        roll, result = roll_random_event_focus()
        return jsonify({"roll": roll, "result": result})
    elif table == "meaning_actions":
        roll = random.randint(1, 200)
        result = MEANING_ACTIONS.get(roll, "Inconnu")
        return jsonify({"roll": roll, "result": result})
    elif table == "meaning_descriptors":
        roll = random.randint(1, 100)
        result = MEANING_DESCRIPTORS.get(roll, "Inconnu")
        return jsonify({"roll": roll, "result": result})
    elif table == "character_elements":
        roll = random.randint(1, 100)
        result = MEANING_ELEMENTS_CHARACTER.get(roll, "Inconnu")
        return jsonify({"roll": roll, "result": result})
    elif table == "object_elements":
        roll = random.randint(1, 100)
        result = MEANING_ELEMENTS_OBJECT.get(roll, "Inconnu")
        return jsonify({"roll": roll, "result": result})
    elif table == "DESCRIPTEURS_CRÉATURE":
        roll = random.randint(1, 100)
        result = DESCRIPTEURS_CRÉATURE.get(roll, "Inconnu")
        return jsonify({"roll": roll, "result": result})
    elif table == "MESSAGE_CRYPTIQUE":
        roll = random.randint(1, 100)
        result = MESSAGE_CRYPTIQUE.get(roll, "Inconnu")
        return jsonify({"roll": roll, "result": result})
    elif table == "MALEDICTIONS":
        roll = random.randint(1, 100)
        result = MALEDICTIONS.get(roll, "Inconnu")
        return jsonify({"roll": roll, "result": result})
    elif table == "DESCRIPTEURS_DOMICILE":
        roll = random.randint(1, 100)
        result = DESCRIPTEURS_DOMICILE.get(roll, "Inconnu")
        return jsonify({"roll": roll, "result": result})
    elif table == "DESCRIPTEURS_DONJON":
        roll = random.randint(1, 100)
        result = DESCRIPTEURS_DONJON.get(roll, "Inconnu")
        print(result)
        return jsonify({"roll": roll, "result": result})
    elif table == "PIÈGES_DONJON":
        roll = random.randint(1, 100)
        result = PIÈGES_DONJON.get(roll, "Inconnu")
        return jsonify({"roll": roll, "result": result})
    elif table == "DESCRIPTEURS_FORÊT":
        roll = random.randint(1, 100)
        result = DESCRIPTEURS_FORÊT.get(roll, "Inconnu")
        return jsonify({"roll": roll, "result": result})
    elif table == "DIEUX":
        roll = random.randint(1, 100)
        result = DIEUX.get(roll, "Inconnu")
        return jsonify({"roll": roll, "result": result})
    elif table == "LÉGENDES":
        roll = random.randint(1, 100)
        result = LÉGENDES.get(roll, "Inconnu")
        return jsonify({"roll": roll, "result": result})
    elif table == "EMPLACEMENTS":
        roll = random.randint(1, 100)
        result = EMPLACEMENTS.get(roll, "Inconnu")
        return jsonify({"roll": roll, "result": result})
    elif table == "DESCRIPTEURS_OBJET_MAGIQUE":
        roll = random.randint(1, 100)
        result = DESCRIPTEURS_OBJET_MAGIQUE.get(roll, "Inconnu")
        return jsonify({"roll": roll, "result": result})
    elif table == "DESCRIPTEURS_MUTATION":
        roll = random.randint(1, 100)
        result = DESCRIPTEURS_MUTATION.get(roll, "Inconnu")
        return jsonify({"roll": roll, "result": result})
    elif table == "NOMS":
        roll = random.randint(1, 100)
        result = NOMS.get(roll, "Inconnu")
        return jsonify({"roll": roll, "result": result})
    elif table == "MAISON_NOBLE":
        roll = random.randint(1, 100)
        result = MAISON_NOBLE.get(roll, "Inconnu")
        return jsonify({"roll": roll, "result": result})
    elif table == "OBJETS":
        roll = random.randint(1, 100)
        result = OBJETS.get(roll, "Inconnu")
        return jsonify({"roll": roll, "result": result})
    elif table == "REBONDISSEMENTS":
        roll = random.randint(1, 100)
        result = REBONDISSEMENTS.get(roll, "Inconnu")
        return jsonify({"roll": roll, "result": result})
    elif table == "POUVOIRS":
        roll = random.randint(1, 100)
        result = POUVOIRS.get(roll, "Inconnu")
        return jsonify({"roll": roll, "result": result})
    elif table == "RÉSULTATS_FOUILLE":
        roll = random.randint(1, 100)
        result = RÉSULTATS_FOUILLE.get(roll, "Inconnu")
        return jsonify({"roll": roll, "result": result})
    elif table == "ODEURS":
        roll = random.randint(1, 100)
        result = ODEURS.get(roll, "Inconnu")
        return jsonify({"roll": roll, "result": result})
    elif table == "SONS":
        roll = random.randint(1, 100)
        result = SONS.get(roll, "Inconnu")
        return jsonify({"roll": roll, "result": result})
    elif table == "EFFETS_SORTS":
        roll = random.randint(1, 100)
        result = EFFETS_SORTS.get(roll, "Inconnu")
        return jsonify({"roll": roll, "result": result})
    elif table == "DESCRIPTEURS_VAISSEAU":
        roll = random.randint(1, 100)
        result = DESCRIPTEURS_VAISSEAU.get(roll, "Inconnu")
        return jsonify({"roll": roll, "result": result})
    elif table == "DESCRIPTEURS_TERRAIN":
        roll = random.randint(1, 100)
        result = DESCRIPTEURS_TERRAIN.get(roll, "Inconnu")
        return jsonify({"roll": roll, "result": result})
    elif table == "DESCRIPTEURS_MORTS_VIVANTS":
        roll = random.randint(1, 100)
        result = DESCRIPTEURS_MORTS_VIVANTS.get(roll, "Inconnu")
        return jsonify({"roll": roll, "result": result})
    elif table == "VISIONS_RÊVES":
        roll = random.randint(1, 100)
        result = VISIONS_RÊVES.get(roll, "Inconnu")
        return jsonify({"roll": roll, "result": result})
    else:
        return jsonify({"error": "Table non définie"})

@app.route("/add_custom_table", methods=["POST"])
def add_custom_table():
    name = request.form.get("customTableName").strip()
    values = request.form.get("customTableValues").strip()
    if name and values:
        new_table = CustomTable(name=name, values=values)
        db.session.add(new_table)
        db.session.commit()
    return redirect(url_for("index") + "#tables")

@app.route("/delete_custom_table/<int:table_id>")
def delete_custom_table(table_id):
    table = CustomTable.query.get_or_404(table_id)
    db.session.delete(table)
    db.session.commit()
    return redirect(url_for("index") + "#tables")

@app.route("/edit_custom_table/<int:table_id>", methods=["POST"])
def edit_custom_table(table_id):
    print('edit !')
    table = CustomTable.query.get_or_404(table_id)
    table.name = request.form.get("customTableNameEdit").strip()
    table.values = request.form.get("customTableValuesEdit").strip()
    db.session.commit()
    return redirect(url_for("index") + "#tables")

@app.route("/get_custom_table")
def get_custom_table():
    table_id = request.args.get("table_id")
    table = CustomTable.query.get(table_id)
    if table:
        return jsonify({"values": table.values})
    else:
        return jsonify({"error": "Table non trouvée"})

@app.route("/add_player", methods=["POST"])
def add_player():
    name = request.form.get("name").strip()
    description = request.form.get("description").strip()
    if name:
        new_player = PlayerCharacter(name=name, description=description)
        db.session.add(new_player)
        db.session.commit()
    return redirect(url_for("index") + "#players")

@app.route("/delete_player/<int:player_id>")
def delete_player(player_id):
    player = PlayerCharacter.query.get_or_404(player_id)
    db.session.delete(player)
    db.session.commit()
    return redirect(url_for("index") + "#players")

@app.route("/add_player_attribute/<int:player_id>", methods=["POST"])
def add_player_attribute(player_id):
    attr_name = request.form.get("attribute_name").strip()
    attr_value = request.form.get("attribute_value").strip()
    is_numeric = request.form.get("is_numeric") == "on"  # True si coché

    # Vérification côté serveur
    if is_numeric:
        try:
            int(attr_value)  # Essayer de convertir en entier
        except ValueError:
            flash("⚠️ La valeur doit être un nombre si 'Numérique' est coché.", "danger")
            return redirect(url_for("index") + "#players")

    new_attr = PlayerAttribute(
        character_id=player_id,
        attribute_name=attr_name,
        attribute_value=attr_value,
        is_numeric=is_numeric
    )
    db.session.add(new_attr)
    db.session.commit()
    return redirect(url_for("index") + "#players")

@app.route("/delete_player_attribute/<int:attribute_id>")
def delete_player_attribute(attribute_id):
    attribute = PlayerAttribute.query.get_or_404(attribute_id)
    db.session.delete(attribute)
    db.session.commit()
    return redirect(url_for("index") + "#players")

@app.route("/edit_player_description/<int:player_id>", methods=["POST"])
def edit_player_description(player_id):
    player = PlayerCharacter.query.get_or_404(player_id)
    player.description = request.form.get("description").strip()
    db.session.commit()
    return redirect(url_for("index") + "#players")

@app.route("/update_chaos", methods=["POST"])
def update_chaos():
    adjustment = int(request.form.get("adjustment"))
    game_state = GameState.query.first()
    game_state.chaos_factor = max(1, min(9, game_state.chaos_factor + adjustment))
    db.session.commit()
    return jsonify({"new_chaos": game_state.chaos_factor})

@app.route("/roll_dice/<int:faces>")
def roll_dice(faces):
    if faces < 1:
        return jsonify({"error": "Nombre de faces invalide"}), 400
    roll = random.randint(1, faces)
    # Sauvegarder le lancer dans la base SQL
    new_roll = DiceRollHistory(faces=faces, roll=roll)
    db.session.add(new_roll)
    db.session.commit()
    return jsonify({"roll": roll, "faces": faces})

@app.route("/dice_history")
def dice_history():
    history = DiceRollHistory.query.order_by(DiceRollHistory.date.desc()).limit(10).all()
    # On prépare une liste de dictionnaires pour le JSON
    history_list = [{
        "date": entry.date.strftime("%Y-%m-%d %H:%M:%S"),
        "faces": entry.faces,
        "roll": entry.roll
    } for entry in history]
    return jsonify(history_list)

if __name__ == "__main__":
    app.run(debug=True)
