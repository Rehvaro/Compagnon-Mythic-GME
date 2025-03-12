from flask import Flask, render_template, request, redirect, url_for, jsonify, flash
from flask_sqlalchemy import SQLAlchemy
from flask_httpauth import HTTPBasicAuth
from werkzeug.security import generate_password_hash, check_password_hash
import random
import json
from datetime import datetime
from flask import Response
from openai import OpenAI
import os

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///mythic_gme.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = 'cle_secrete_mythic'

db = SQLAlchemy(app)
auth = HTTPBasicAuth()

# Utilisateurs pour l'authentification
users = {
    "admin": generate_password_hash("motdepasse")
}

@auth.verify_password
def verify_password(username, password):
    if username in users and check_password_hash(users.get(username), password):
        return username

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

class OpenAIConfig(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    api_key = db.Column(db.String(200), nullable=True)

with app.app_context():
    db.create_all()
    if not OpenAIConfig.query.first():
        db.session.add(OpenAIConfig(api_key=""))
        db.session.commit()

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
@auth.login_required
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

    openai_config = OpenAIConfig.query.first()

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
                       custom_tables_json=json.dumps([{ "id": t.id, "name": t.name, "values": t.values } for t in custom_tables]),
                       openai_key=openai_config.api_key)


@app.route("/ask_fate", methods=["POST"])
@auth.login_required
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
    return jsonify({"success": True}), 200

@app.route("/delete_fate/<int:question_id>", methods=["POST"])
@auth.login_required
def delete_fate(question_id):
    fq = FateQuestion.query.get_or_404(question_id)
    db.session.delete(fq)
    db.session.commit()
    return jsonify({"success": True}), 200

@app.route("/add_objective", methods=["POST"])
@auth.login_required
def add_objective():
    description = request.form.get("description")
    new_objective = Objective(description=description)
    db.session.add(new_objective)
    db.session.commit()
    return jsonify({"success": True}), 200

@app.route("/delete_objective/<int:objective_id>", methods=["POST"])
@auth.login_required
def delete_objective(objective_id):
    obj = Objective.query.get_or_404(objective_id)
    db.session.delete(obj)
    db.session.commit()
    return jsonify({"success": True}), 200

@app.route("/add_npc", methods=["POST"])
@auth.login_required
def add_npc():
    name = request.form.get("name")
    description = request.form.get("description")
    new_npc = NPC(name=name, description=description)
    db.session.add(new_npc)
    db.session.commit()
    return jsonify({"success": True}), 200

@app.route("/delete_npc/<int:npc_id>", methods=["POST"])
@auth.login_required
def delete_npc(npc_id):
    npc = NPC.query.get_or_404(npc_id)
    db.session.delete(npc)
    db.session.commit()
    return jsonify({"success": True}), 200

@app.route("/random_npc", methods=["POST"])
@auth.login_required
def random_npc():
    npcs = NPC.query.all()
    if npcs:
        npc = random.choice(npcs)
        return jsonify({"name": npc.name, "description": npc.description})
    else:
        return jsonify({"error": "Aucun PNJ enregistré."})

@app.route("/add_scene", methods=["POST"])
@auth.login_required
def add_scene():
    title = request.form.get("title")
    description = request.form.get("description")
    status = request.form.get("status", "normale")
    new_scene = Scene(title=title, description=description, status=status)
    db.session.add(new_scene)
    db.session.commit()
    return jsonify({"success": True}), 200

@app.route("/delete_scene/<int:scene_id>", methods=["POST"])
@auth.login_required
def delete_scene(scene_id):
    scene = Scene.query.get_or_404(scene_id)
    db.session.delete(scene)
    db.session.commit()
    return jsonify({"success": True}), 200

@app.route("/adjust_chaos", methods=["POST"])
@auth.login_required
def adjust_chaos():
    adjustment = int(request.form.get("adjustment"))
    game_state = GameState.query.first()
    game_state.chaos_factor = max(1, min(9, game_state.chaos_factor + adjustment))
    db.session.commit()
    return jsonify({"success": True}), 200

# Endpoint pour le Chaos Roll des scènes sur d10
@app.route("/scene_chaos_roll", methods=["POST"])
@auth.login_required
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
@app.route("/roll_d100", methods=["POST"])
@auth.login_required
def roll_d100():
    roll = random.randint(1, 100)
    return jsonify({"roll": roll})

@app.route("/journal", defaults={'page': 1}, methods=["POST"])
@app.route("/journal/page/<int:page>", methods=["POST"])
@auth.login_required
def journal(page):
    per_page = 5  # Nombre d'entrées par page
    journal_entries = JournalEntry.query.order_by(JournalEntry.date.desc()).paginate(page=page, per_page=per_page, error_out=False)
    fate_page = request.args.get('fate_page', 1, type=int)
    fate_questions = FateQuestion.query.order_by(FateQuestion.id.desc()).paginate(page=fate_page, per_page=6, error_out=False)
    print(journal_entries)
    return render_template("index.html", journal_entries=journal_entries, current_page=page)

@app.route("/add_journal_entry", methods=["POST"])
@auth.login_required
def add_journal_entry():
    content = request.form.get("content").strip()
    if content:
        new_entry = JournalEntry(content=content)
        db.session.add(new_entry)
        db.session.commit()
    return jsonify({"success": True}), 200

@app.route("/delete_journal_entry/<int:entry_id>", methods=["POST"])
@auth.login_required
def delete_journal_entry(entry_id):
    entry = JournalEntry.query.get_or_404(entry_id)
    db.session.delete(entry)
    db.session.commit()
    return jsonify({"success": True}), 200

@app.route("/export_journal", methods=["POST"])
@auth.login_required
def export_journal():
    entries = JournalEntry.query.order_by(JournalEntry.date.asc()).all()
    markdown_content = "# Journal\n\n"
    for entry in entries:
        markdown_content += f"## {entry.date.strftime('%Y-%m-%d %H:%M:%S')}\n\n{entry.content}\n\n---\n\n"
    
    return Response(markdown_content, mimetype="text/markdown", headers={"Content-Disposition": "attachment;filename=journal.md"})

@app.route("/add_inventory", methods=["POST"])
@auth.login_required
def add_inventory():
    title = request.form.get("title").strip()
    if title:
        new_inventory = Inventory(title=title)
        db.session.add(new_inventory)
        print(new_inventory)
        db.session.commit()
    return jsonify({"success": True}), 200

@app.route("/delete_inventory/<int:inventory_id>", methods=["POST"])
@auth.login_required
def delete_inventory(inventory_id):
    inventory = Inventory.query.get_or_404(inventory_id)
    db.session.delete(inventory)
    db.session.commit()
    return jsonify({"success": True}), 200

@app.route("/add_inventory_item/<int:inventory_id>", methods=["POST"])
@auth.login_required
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
    return jsonify({"success": True}), 200

@app.route("/delete_inventory_item/<int:item_id>", methods=["POST"])
@auth.login_required
def delete_inventory_item(item_id):
    item = InventoryItem.query.get_or_404(item_id)
    db.session.delete(item)
    db.session.commit()
    return jsonify({"success": True}), 200

@app.route("/update_attribute/<int:attribute_id>/<string:operation>", methods=["POST"])
@auth.login_required
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
@auth.login_required
def update_item_quantity(item_id, operation):
    item = InventoryItem.query.get_or_404(item_id)
    if operation == "increase":
        item.quantity += 1
    elif operation == "decrease" and item.quantity > 0:
        item.quantity -= 1
    db.session.commit()
    return jsonify({"success": True, "new_quantity": item.quantity, "inventory_id": item.inventory_id})

@app.route("/update_openai_key", methods=["POST"])
@auth.login_required
def update_openai_key():
    api_key = request.form.get("api_key")
    config = OpenAIConfig.query.first()
    if config:
        config.api_key = api_key
    else:
        config = OpenAIConfig(api_key=api_key)
        db.session.add(config)
    db.session.commit()
    flash("Clé OpenAI mise à jour avec succès.", "success")
    return redirect(url_for("index") + "#options")

@app.route("/transcribe_audio", methods=["POST"])
@auth.login_required
def transcribe_audio():
    config = OpenAIConfig.query.first()
    if not config or not config.api_key:
        return jsonify({"error": "Clé API OpenAI non configurée."}), 400

    audio_file = request.files["audio"]
    audio_blob = audio_file.read()  # Read the file content as bytes
    audio_file_path = "temp_audio.wav"
    
    # Save the audio blob to a temporary file
    with open(audio_file_path, "wb") as f:
        f.write(audio_blob)

    client = OpenAI(api_key=config.api_key)
    with open(audio_file_path, "rb") as f:
        transcription = client.audio.transcriptions.create(
            model="whisper-1",
            file=f,
            response_format="json"
        )
    
    # Optionally, remove the temporary file after processing
    os.remove(audio_file_path)

    # Access the transcription text directly
    transcription_text = transcription.text if hasattr(transcription, 'text') else ""
    
    return jsonify({"transcription": transcription_text})

@app.route("/reformat_journal", methods=["POST"])
@auth.login_required
def reformat_journal():
    text = request.form.get("journal_text")
    config = OpenAIConfig.query.first()
    
    if not config or not config.api_key:
        return jsonify({"error": "Aucune clé OpenAI configurée."}), 400

    client = OpenAI(api_key=config.api_key)

    try:
        response = client.chat.completions.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content":
                 """
                 Tu es un assistant de jeu de rôle spécialisé dans la reformulation de résumés de sessions de JDR. 
                 Réalise un document résumant cette scène de JDR Solo en respectant ce format :
                 ### Résumé
                 Ici tu met le résumé naré de la scène
                 ### Résumé en liste à puce
                 Ici tu fait un résumé chronologique des elements importants du recit sous forme de listes a puces
                 ### Lieux
                 Ici tu liste les lieux dont parle la session et ce qui en est dit
                 ### Personnages 
                 Ici tu met les personnages sont parle la session, avec ce qui est dit a leur sujet
                 ### Objets
                 Ici tu met les objets importants du recit tel que décris 
                 ### Evolution
                 Ici tu décris l'évolution du lore, cad tel qu'il était avant la scène, comparé a après la scène
                 """ 
                },
                {"role": "user", "content": text}
            ],
            temperature=0.7
        )
        formatted_text = response.choices[0].message.content
        
        return jsonify({"formatted_text": formatted_text})
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    
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
ACTIONS = {
    1: "Attraper", 2: "Briser", 3: "Chasser", 4: "Construire", 5: "Créer",
    6: "Détruire", 7: "Découvrir", 8: "Écouter", 9: "Explorer", 10: "Fouiller",
    11: "Fuir", 12: "Ignorer", 13: "Imiter", 14: "Manipuler", 15: "Obscurcir",
    16: "Poursuivre", 17: "Protéger", 18: "Révéler", 19: "Soumettre", 20: "Transformer"}

DESCRIPTEURS = {
    1: "Abstrait", 2: "Brutal", 3: "Changeant", 4: "Complexe", 5: "Déchiré",
    6: "Étrange", 7: "Fuyant", 8: "Harmonieux", 9: "Instable", 10: "Lourd",
    11: "Méticuleux", 12: "Obscur", 13: "Paisible", 14: "Rigide", 15: "Sombre",
    16: "Tranchant", 17: "Vif", 18: "Volatile", 19: "Fragile", 20: "Intemporel"}

ELEMENT_PERSONNAGE = {
    1: "Amulette", 2: "Armure", 3: "Blessure", 4: "Cicatrice", 5: "Compagnon",
    6: "Cri", 7: "Défiance", 8: "Devise", 9: "Éducation", 10: "Équipement",
    11: "Famille", 12: "Fardeau", 13: "Geste", 14: "Glyphe", 15: "Héritage",
    16: "Instinct", 17: "Lignée", 18: "Regard", 19: "Souvenir", 20: "Tatouage"}

ELEMENT_OBJET = {
    1: "Ancres", 2: "Anneaux", 3: "Arêtes", 4: "Boutons", 5: "Câbles",
    6: "Charmes", 7: "Châssis", 8: "Crochets", 9: "Éclats", 10: "Engrenages",
    11: "Fissures", 12: "Gemmes", 13: "Inscriptions", 14: "Lentilles", 15: "Miroirs",
    16: "Rivets", 17: "Sceaux", 18: "Serrures", 19: "Trappes", 20: "Vis"}

ACTIONS_COMBAT = {
    1: "Absorber", 2: "Acculer", 3: "Assommer", 4: "Bondir", 5: "Bloquer",
    6: "Contre-attaquer", 7: "Désarmer", 8: "Dissiper", 9: "Esquiver", 10: "Exécuter",
    11: "Frapper", 12: "Lancer", 13: "Marteler", 14: "Parer", 15: "Percer",
    16: "Repousser", 17: "Saisir", 18: "Séduire", 19: "Surprendre", 20: "Vaincre"}

APPARENCE = {
    1: "Albinos", 2: "Anguleux", 3: "Cicatriciel", 4: "Cristallin", 5: "Déformé",
    6: "Doré", 7: "Écorché", 8: "Épineux", 9: "Éthéré", 10: "Géométrique",
    11: "Glacial", 12: "Hérissé", 13: "Iridescent", 14: "Lisse", 15: "Marbré",
    16: "Mécanique", 17: "Sinueux", 18: "Tatoué", 19: "Velu", 20: "Voilé"}

IDENTITE_PERSONNAGE = {
    1: "Anonyme", 2: "Banni", 3: "Brisé", 4: "Caché", 5: "Changé",
    6: "Cloné", 7: "Déchu", 8: "Dissimulé", 9: "Errant", 10: "Falsifié",
    11: "Hérité", 12: "Illusoire", 13: "Imité", 14: "Maudit", 15: "Oublié",
    16: "Prophétique", 17: "Renommé", 18: "Secret", 19: "Singulier", 20: "Volé"}

MOTIVATIONS = {
    1: "Ascension", 2: "Conquête", 3: "Création", 4: "Curiosité", 5: "Défi",
    6: "Dévotion", 7: "Équilibre", 8: "Évasion", 9: "Gloire", 10: "Héritage",
    11: "Justice", 12: "Liberté", 13: "Obsession", 14: "Pardon", 15: "Puissance",
    16: "Rédemption", 17: "Revanche", 18: "Richesse", 19: "Savoir", 20: "Survie"}

PERSONNALITE = {
    1: "Affable", 2: "Arrogant", 3: "Audacieux", 4: "Bienveillant", 5: "Boudeur",
    6: "Calculateur", 7: "Charismatique", 8: "Cruel", 9: "Distant", 10: "Excentrique",
    11: "Farouche", 12: "Froid", 13: "Généreux", 14: "Impulsif", 15: "Lâche",
    16: "Mélancolique", 17: "Narcissique", 18: "Obstiné", 19: "Rêveur", 20: "Sévère"}

CAPACITE_PERSONNAGE = {
    1: "Adaptation", 2: "Agilité", 3: "Alchimie", 4: "Analyse", 5: "Camouflage",
    6: "Charisme", 7: "Concentration", 8: "Déduction", 9: "Endurance", 10: "Esquive",
    11: "Force", 12: "Imitation", 13: "Intimidation", 14: "Magie", 15: "Mémoire",
    16: "Précision", 17: "Résistance", 18: "Sang-froid", 19: "Sensibilité", 20: "Vitesse"}

TRAITS_PERSONNAGE = {
    1: "Ambitieux", 2: "Aventurier", 3: "Brave", 4: "Calme", 5: "Déterminé",
    6: "Discipliné", 7: "Empathique", 8: "Fidèle", 9: "Gourmand", 10: "Habile",
    11: "Idéaliste", 12: "Indépendant", 13: "Loyal", 14: "Malin", 15: "Mystérieux",
    16: "Optimiste", 17: "Patient", 18: "Protecteur", 19: "Rancunier", 20: "Sociable"}

DEFAUTS_PERSONNAGE = {
    1: "Agressif", 2: "Borné", 3: "Cupide", 4: "Dédaigneux", 5: "Désinvolte",
    6: "Égocentrique", 7: "Envieux", 8: "Froid", 9: "Fuyant", 10: "Hésitant",
    11: "Inconstant", 12: "Jaloux", 13: "Lâche", 14: "Manipulateur", 15: "Méfiant",
    16: "Négligent", 17: "Obsessionnel", 18: "Peureux", 19: "Taciturne", 20: "Vaniteux"}

DESCRIPTEUR_CITE = {
    1: "Animée", 2: "Brisée", 3: "Cachée", 4: "Chaotique", 5: "Désolée",
    6: "Endormie", 7: "Fascinante", 8: "Fortifiée", 9: "Labyrinthique", 10: "Luxuriante",
    11: "Mystique", 12: "Nostalgique", 13: "Opulente", 14: "Perdue", 15: "Ravagée",
    16: "Sacrée", 17: "Souterraine", 18: "Technologique", 19: "Troublée", 20: "Vibrante"}

DESCRIPTEUR_CIVILISATION = {
    1: "Actif", 2: "Avancé", 3: "Aventureux", 4: "Agressif", 5: "Agricole",
    6: "Ancien", 7: "En colère", 8: "Anxieux", 9: "Artistique", 10: "Moyen",
    11: "Beau", 12: "Bizarre", 13: "Sombre", 14: "Audacieux", 15: "Bureaucratique",
    16: "Insouciant", 17: "Prudent", 18: "Négligent", 19: "Précautionneux", 20: "Chic"}

CAPACITE_CREATURE = {
    1: "Camouflage", 2: "Étreinte mortelle", 3: "Régénération", 4: "Vision nocturne", 5: "Télépathie",
    6: "Résistance au feu", 7: "Résistance magique", 8: "Force colossale", 9: "Vol", 10: "Souterrain",
    11: "Vitesse surnaturelle", 12: "Hurlement terrifiant", 13: "Empoisonnement", 14: "Intelligence supérieure", 15: "Mutation rapide",
    16: "Contrôle des ombres", 17: "Absorption d'énergie", 18: "Cri paralysant", 19: "Métamorphose", 20: "Invocation de sbires"}

DESCRIPTEUR_CREATURE = {
    1: "Bestial", 2: "Chthonien", 3: "Colossal", 4: "Cryptique", 5: "Décrépit",
    6: "Éthéré", 7: "Fantomatique", 8: "Géant", 9: "Hérissé", 10: "Illusoire",
    11: "Luminescent", 12: "Malveillant", 13: "Mutant", 14: "Nocturne", 15: "Ombreux",
    16: "Putride", 17: "Rampant", 18: "Surnaturel", 19: "Terrifiant", 20: "Venimeux"}

MALEDICTIONS = {
    1: "Âme errante", 2: "Anémie vampirique", 3: "Asphyxie éternelle", 4: "Aversion solaire", 5: "Banni des cieux",
    6: "Changement incontrôlable", 7: "Douleur perpétuelle", 8: "Écho spectral", 9: "Faim insatiable", 10: "Fléau des ombres",
    11: "Illusions troublantes", 12: "Immortalité maudite", 13: "Infestation cauchemardesque", 14: "Inversion du destin", 15: "Lente putréfaction",
    16: "Lien avec les ténèbres", 17: "Mémoire brisée", 18: "Obsession incontrôlable", 19: "Poids de la souffrance", 20: "Regard pétrifiant"}

DESCRIPTEUR_DOMICILE = {
    1: "Abandonné", 2: "Brumeux", 3: "Caché", 4: "Confortable", 5: "Délabré",
    6: "Étrange", 7: "Fantaisiste", 8: "Glacial", 9: "Hanté", 10: "Illusoire",
    11: "Joyeux", 12: "Labyrinthique", 13: "Mystique", 14: "Naturel", 15: "Ombreux",
    16: "Paisible", 17: "Ravagé", 18: "Secret", 19: "Souterrain", 20: "Vivant"}

DESCRIPTEUR_DONJON = {
    1: "Ancien", 2: "Brisé", 3: "Construit sur un cimetière", 4: "Désolé", 5: "Enchevêtré",
    6: "Froid", 7: "Glissant", 8: "Hanté", 9: "Illusoire", 10: "Jadis glorieux",
    11: "Karmique", 12: "Labyrinthique", 13: "Mystérieux", 14: "Négligé", 15: "Obscur",
    16: "Perdu", 17: "Ravagé", 18: "Saturé de magie", 19: "Traître", 20: "Vaste"}

PIEGE_DONJON = {
    1: "Acide caché", 2: "Brouillard hallucinogène", 3: "Chute dissimulée", 4: "Corde enchantée", 5: "Dalles mouvantes",
    6: "Éclats maudits", 7: "Flèches empoisonnées", 8: "Geyser de flammes", 9: "Illusions trompeuses", 10: "Jet de glace",
    11: "Kystes explosifs", 12: "Labyrinthe piégé", 13: "Mur écrasant", 14: "Nappe d’huile", 15: "Orbe de tonnerre",
    16: "Piège à vent", 17: "Quicksand", 18: "Rayon désintégrant", 19: "Statue animée", 20: "Trappe sans fond"}

DESCRIPTEUR_FORET = {
    1: "Ancestrale", 2: "Brumeuse", 3: "Calme", 4: "Dense", 5: "Enchanteresse",
    6: "Flamboyante", 7: "Glaciale", 8: "Hostile", 9: "Illusoire", 10: "Jungle étouffante",
    11: "Karmique", 12: "Luxuriante", 13: "Malsaine", 14: "Nébuleuse", 15: "Obscure",
    16: "Perdue", 17: "Ravagée", 18: "Surnaturelle", 19: "Ténébreuse", 20: "Vénéneuse"}

DIEUX = {
    1: "Ancien", 2: "Colérique", 3: "Créateur", 4: "Cruel", 5: "Disparu",
    6: "Énigmatique", 7: "Exilé", 8: "Façonnant", 9: "Généreux", 10: "Indifférent",
    11: "Jaloux", 12: "Lointain", 13: "Menaçant", 14: "Mystérieux", 15: "Oublié",
    16: "Protecteur", 17: "Rival", 18: "Sanguinaire", 19: "Silencieux", 20: "Vengeur"}

LEGENDES = {
    1: "Âge d’or", 2: "Artefact perdu", 3: "Bataille mythique", 4: "Cité engloutie", 5: "Création divine",
    6: "Destin maudit", 7: "Dieu tombé", 8: "Élixir d'immortalité", 9: "Élu", 10: "Empire disparu",
    11: "Fléau ancestral", 12: "Gardien oublié", 13: "Héros tragique", 14: "Malédiction séculaire", 15: "Métamorphose divine",
    16: "Monstre endormi", 17: "Prophétie brisée", 18: "Royaume caché", 19: "Trésor interdit", 20: "Voyage impossible"}

LIEUX = {
    1: "Abîme sans fond", 2: "Autel maudit", 3: "Canyon embrumé", 4: "Caverne cristalline", 5: "Cité suspendue",
    6: "Désert chantant", 7: "Forteresse oubliée", 8: "Île mouvante", 9: "Jungle étouffante", 10: "Labyrinthe sans fin",
    11: "Marais pestilentiel", 12: "Montagne creuse", 13: "Palais fantôme", 14: "Porte dimensionnelle", 15: "Prison interdite",
    16: "Ruines englouties", 17: "Sanctuaire interdit", 18: "Temple inversé", 19: "Tour infinie", 20: "Vallée du néant"}

DESCRIPTEURS_OBJETS_MAGIQUES = {
    1: "Ancestral", 2: "Brisé", 3: "Changeant", 4: "Chuchotant", 5: "Conscient",
    6: "Corrompu", 7: "Disparu", 8: "Énergétique", 9: "Évolutif", 10: "Foudroyant",
    11: "Illusoire", 12: "Incomplet", 13: "Instable", 14: "Légendaire", 15: "Maudit",
    16: "Miroitant", 17: "Protecteur", 18: "Renaissant", 19: "Sanglant", 20: "Sombre"}

MUTATION = {
    1: "Ailes membraneuses", 2: "Apparence spectrale", 3: "Bras multiples", 4: "Carapace chitineuse", 5: "Corps translucide",
    6: "Crâne fendu", 7: "Doigts allongés", 8: "Écailles de fer", 9: "Épine dorsale exposée", 10: "Flammes internes",
    11: "Gueule béante", 12: "Lumière intérieure", 13: "Membres inversés", 14: "Miroir vivant", 15: "Œil unique",
    16: "Ombre mouvante", 17: "Peau changeante", 18: "Silhouette floue", 19: "Tête éclatée", 20: "Tentacules dorsaux"}

DESCRIPTEUR_NOMS = {
    1: "Austère", 2: "Brisé", 3: "Chantant", 4: "Cryptique", 5: "Déchu",
    6: "Égaré", 7: "Éphémère", 8: "Flamboyant", 9: "Fragmenté", 10: "Héritier",
    11: "Insaisissable", 12: "Légendaire", 13: "Mystique", 14: "Obscur", 15: "Oublié",
    16: "Renaissant", 17: "Secret", 18: "Sévère", 19: "Vibrant", 20: "Volatile"}

SYLLABE_NOMS = {
    1: "Ar", 2: "Bel", 3: "Cra", 4: "Dor", 5: "Fen",
    6: "Gar", 7: "Hel", 8: "Jor", 9: "Kal", 10: "Lor",
    11: "Mel", 12: "Nor", 13: "Or", 14: "Pol", 15: "Quin",
    16: "Ral", 17: "Ser", 18: "Tor", 19: "Ul", 20: "Vor"}

POUVOIR = {
    1: "Absorption", 2: "Altération du temps", 3: "Armure vivante", 4: "Camouflage total", 5: "Contrôle des ombres",
    6: "Création d’illusions", 7: "Décharge d’énergie", 8: "Empathie animale", 9: "Fléau instantané", 10: "Fusion élémentaire",
    11: "Guérison absolue", 12: "Immortalité partielle", 13: "Invocation d’entités", 14: "Mimétisme", 15: "Portail dimensionnel",
    16: "Prémonition", 17: "Regard pétrifiant", 18: "Télékinésie", 19: "Transmutation", 20: "Voyance"}

RÊVE = {
    1: "Abîme infini", 2: "Appel d’une voix inconnue", 3: "Brume impénétrable", 4: "Cité en ruine", 5: "Cri dans le vide",
    6: "Danse macabre", 7: "Déformation du monde", 8: "Éclats de mémoire", 9: "Écho d’un futur incertain", 10: "Forêt de cristal",
    11: "Lac aux reflets mouvants", 12: "Labyrinthe vivant", 13: "Main invisible", 14: "Masque sans visage", 15: "Montagnes flottantes",
    16: "Murmures insidieux", 17: "Ombres animées", 18: "Pluie d’étoiles", 19: "Renaissance perpétuelle", 20: "Sommeil sans fin"}

REBONDISSEMENT = {
    1: "Allié trahi", 2: "Ancienne prophétie révélée", 3: "Apparition soudaine", 4: "Changement de camp", 5: "Chantage inattendu",
    6: "Coupable innocenté", 7: "Détour obligatoire", 8: "Double jeu découvert", 9: "Ennemi devenu allié", 10: "Erreur fatale",
    11: "Faux indice", 12: "Fausse mort", 13: "Identité secrète dévoilée", 14: "Mauvaise interprétation", 15: "Mémoire retrouvée",
    16: "Mission sabotée", 17: "Objet clé détruit", 18: "Plan démasqué", 19: "Rencontre du passé", 20: "Trahison intérieure"}

RÉSULTAT_DE_FOUILLE = {
    1: "Amulette cassée", 2: "Anneau gravé", 3: "Carte incomplète", 4: "Clé étrange", 5: "Coffre vide",
    6: "Contrat signé", 7: "Cristal fissuré", 8: "Dague ensanglantée", 9: "Journal déchiré", 10: "Lettre codée",
    11: "Médaille d’un ordre disparu", 12: "Monnaie ancienne", 13: "Morceau d’armure", 14: "Parchemin brûlé", 15: "Perle noire",
    16: "Petite figurine en os", 17: "Potion instable", 18: "Sceau royal", 19: "Statue miniature", 20: "Verre contenant un liquide inconnu"}

ODEUR = {
    1: "Acide", 2: "Ambrée", 3: "Brûlé", 4: "Cendreux", 5: "Charnel",
    6: "Citronné", 7: "Doux", 8: "Épicé", 9: "Ferreux", 10: "Fétide",
    11: "Florale", 12: "Humide", 13: "Mielleuse", 14: "Moisie", 15: "Morte",
    16: "Poissonneuse", 17: "Putride", 18: "Résineuse", 19: "Soufrée", 20: "Vinaigrée"}

SONS = {
    1: "Bourdonnement constant", 2: "Chant lointain", 3: "Cloche sourde", 4: "Cri perçant", 5: "Détonation étouffée",
    6: "Écho troublant", 7: "Froissement rapide", 8: "Grattement lent", 9: "Hurlement spectral", 10: "Murmure indistinct",
    11: "Palpitations sourdes", 12: "Râle prolongé", 13: "Ricanement moqueur", 14: "Ronronnement métallique", 15: "Ruissellement discret",
    16: "Sifflement strident", 17: "Tic-tac régulier", 18: "Tremblement sourd", 19: "Vibration aiguë", 20: "Voix sans source"}

EFFET_DE_SORT = {
    1: "Absorption d’énergie", 2: "Altération du temps", 3: "Aura brûlante", 4: "Chaleur écrasante", 5: "Changement d’apparence",
    6: "Chute de température", 7: "Déformation de l’espace", 8: "Détection de pensées", 9: "Distorsion sonore", 10: "Éclair aveuglant",
    11: "Explosion d’ombres", 12: "Illusions persistantes", 13: "Invulnérabilité temporaire", 14: "Lévitation imprévue", 15: "Lumière surnaturelle",
    16: "Métamorphose forcée", 17: "Portail éphémère", 18: "Résonance magique", 19: "Téléportation partielle", 20: "Vision multiple"}

DESCRIPTEUR_VAISSEAU_SPATIAL = {
    1: "Ancien", 2: "Brisé", 3: "Camouflé", 4: "Colossal", 5: "Cyclopéen",
    6: "Discret", 7: "Épave", 8: "Furtif", 9: "Gigantesque", 10: "Invisible",
    11: "Labyrinthique", 12: "Maudit", 13: "Modulaire", 14: "Obsolète", 15: "Organique",
    16: "Prototypique", 17: "Réparé de fortune", 18: "Sentient", 19: "Silencieux", 20: "Vivant"}

DESCRIPTEUR_TERRAIN = {
    1: "Aride", 2: "Boueux", 3: "Brumeux", 4: "Caverneux", 5: "Chaotique",
    6: "Cristallin", 7: "Déchiqueté", 8: "Électrique", 9: "Embrasé", 10: "Érodé",
    11: "Fertile", 12: "Flottant", 13: "Gelé", 14: "Instable", 15: "Labyrinthique",
    16: "Luxuriant", 17: "Mouvant", 18: "Poisseux", 19: "Toxique", 20: "Volcanique"}

DESCRIPTEUR_MORT_VIVANT = {
    1: "Affamé", 2: "Agonisant", 3: "Altéré", 4: "Brisé", 5: "Cadavérique",
    6: "Décharné", 7: "Déformé", 8: "Écorché", 9: "Éthéré", 10: "Fongique",
    11: "Gelé", 12: "Gémissant", 13: "Hanté", 14: "Incomplet", 15: "Lugubre",
    16: "Miasmatique", 17: "Putréfié", 18: "Silencieux", 19: "Squelettique", 20: "Spectral"}


@app.route("/roll_table", methods=["POST"])
@auth.login_required
def roll_table():
    table = request.args.get("table")
    if table == "scene_adjustment":
        roll = random.randint(1, 10)
        result = SCENE_ADJUSTMENT_TABLE.get(roll, "Inconnu")
        return jsonify({"roll": roll, "result": result})
    elif table == "random_event_focus":
        roll, result = roll_random_event_focus()
        return jsonify({"roll": roll, "result": result})
    elif table == "ACTIONS":
        roll = random.randint(1, 20)
        result = ACTIONS.get(roll, "Inconnu")
        return jsonify({"roll": roll, "result": result})
    elif table == "DESCRIPTEURS":
        roll = random.randint(1, 20)
        result = DESCRIPTEURS.get(roll, "Inconnu")
        return jsonify({"roll": roll, "result": result})
    elif table == "ELEMENT_PERSONNAGE":
        roll = random.randint(1, 20)
        result = ELEMENT_PERSONNAGE.get(roll, "Inconnu")
        return jsonify({"roll": roll, "result": result})
    elif table == "ELEMENT_OBJET":
        roll = random.randint(1, 20)
        result = ELEMENT_OBJET.get(roll, "Inconnu")
        return jsonify({"roll": roll, "result": result})
    elif table == "ACTIONS_COMBAT":
        roll = random.randint(1, 20)
        result = ACTIONS_COMBAT.get(roll, "Inconnu")
        return jsonify({"roll": roll, "result": result})
    elif table == "APPARENCE":
        roll = random.randint(1, 20)
        result = APPARENCE.get(roll, "Inconnu")
        return jsonify({"roll": roll, "result": result})
    elif table == "IDENTITE_PERSONNAGE":
        roll = random.randint(1, 20)
        result = IDENTITE_PERSONNAGE.get(roll, "Inconnu")
        return jsonify({"roll": roll, "result": result})
    elif table == "MOTIVATIONS":
        roll = random.randint(1, 20)
        result = MOTIVATIONS.get(roll, "Inconnu")
        return jsonify({"roll": roll, "result": result})
    elif table == "PERSONNALITE":
        roll = random.randint(1, 20)
        result = PERSONNALITE.get(roll, "Inconnu")
        return jsonify({"roll": roll, "result": result})
    elif table == "CAPACITE_PERSONNAGE":
        roll = random.randint(1, 20)
        result = CAPACITE_PERSONNAGE.get(roll, "Inconnu")
        return jsonify({"roll": roll, "result": result})
    elif table == "TRAITS_PERSONNAGE":
        roll = random.randint(1, 20)
        result = TRAITS_PERSONNAGE.get(roll, "Inconnu")
        return jsonify({"roll": roll, "result": result})
    elif table == "DEFAUTS_PERSONNAGE":
        roll = random.randint(1, 20)
        result = DEFAUTS_PERSONNAGE.get(roll, "Inconnu")
        return jsonify({"roll": roll, "result": result})
    elif table == "DESCRIPTEUR_CITE":
        roll = random.randint(1, 20)
        result = DESCRIPTEUR_CITE.get(roll, "Inconnu")
        return jsonify({"roll": roll, "result": result})
    elif table == "DESCRIPTEUR_CIVILISATION":
        roll = random.randint(1, 20)
        result = DESCRIPTEUR_CIVILISATION.get(roll, "Inconnu")
        return jsonify({"roll": roll, "result": result})
    elif table == "CAPACITE_CREATURE":
        roll = random.randint(1, 20)
        result = CAPACITE_CREATURE.get(roll, "Inconnu")
        return jsonify({"roll": roll, "result": result})
    elif table == "DESCRIPTEUR_CREATURE":
        roll = random.randint(1, 20)
        result = DESCRIPTEUR_CREATURE.get(roll, "Inconnu")
        return jsonify({"roll": roll, "result": result})
    elif table == "MALEDICTIONS":
        roll = random.randint(1, 20)
        result = MALEDICTIONS.get(roll, "Inconnu")
        return jsonify({"roll": roll, "result": result})
    elif table == "DESCRIPTEUR_DOMICILE":
        roll = random.randint(1, 20)
        result = DESCRIPTEUR_DOMICILE.get(roll, "Inconnu")
        return jsonify({"roll": roll, "result": result})
    elif table == "DESCRIPTEUR_DONJON":
        roll = random.randint(1, 20)
        result = DESCRIPTEUR_DONJON.get(roll, "Inconnu")
        return jsonify({"roll": roll, "result": result})
    elif table == "PIEGE_DONJON":
        roll = random.randint(1, 20)
        result = PIEGE_DONJON.get(roll, "Inconnu")
        return jsonify({"roll": roll, "result": result})
    elif table == "DESCRIPTEUR_FORET":
        roll = random.randint(1, 20)
        result = DESCRIPTEUR_FORET.get(roll, "Inconnu")
        return jsonify({"roll": roll, "result": result})
    elif table == "DIEUX":
        roll = random.randint(1, 20)
        result = DIEUX.get(roll, "Inconnu")
        return jsonify({"roll": roll, "result": result})
    elif table == "LEGENDES":
        roll = random.randint(1, 20)
        result = LEGENDES.get(roll, "Inconnu")
        return jsonify({"roll": roll, "result": result})
    elif table == "LIEUX":
        roll = random.randint(1, 20)
        result = LIEUX.get(roll, "Inconnu")
        return jsonify({"roll": roll, "result": result})
    elif table == "DESCRIPTEURS_OBJETS_MAGIQUES":
        roll = random.randint(1, 20)
        result = DESCRIPTEURS_OBJETS_MAGIQUES.get(roll, "Inconnu")
        return jsonify({"roll": roll, "result": result})
    elif table == "MUTATION":
        roll = random.randint(1, 20)
        result = MUTATION.get(roll, "Inconnu")
        return jsonify({"roll": roll, "result": result})
    elif table == "DESCRIPTEUR_NOMS":
        roll = random.randint(1, 20)
        result = DESCRIPTEUR_NOMS.get(roll, "Inconnu")
        return jsonify({"roll": roll, "result": result})
    elif table == "SYLLABE_NOMS":
        roll = random.randint(1, 20)
        result = SYLLABE_NOMS.get(roll, "Inconnu")
        return jsonify({"roll": roll, "result": result})
    elif table == "POUVOIR":
        roll = random.randint(1, 20)
        result = POUVOIR.get(roll, "Inconnu")
        return jsonify({"roll": roll, "result": result})
    elif table == "RÊVE":
        roll = random.randint(1, 20)
        result = RÊVE.get(roll, "Inconnu")
        return jsonify({"roll": roll, "result": result})
    elif table == "REBONDISSEMENT":
        roll = random.randint(1, 20)
        result = REBONDISSEMENT.get(roll, "Inconnu")
        return jsonify({"roll": roll, "result": result})
    elif table == "RÉSULTAT_DE_FOUILLE":
        roll = random.randint(1, 20)
        result = RÉSULTAT_DE_FOUILLE.get(roll, "Inconnu")
        return jsonify({"roll": roll, "result": result})
    elif table == "ODEUR":
        roll = random.randint(1, 20)
        result = ODEUR.get(roll, "Inconnu")
        return jsonify({"roll": roll, "result": result})
    elif table == "SONS":
        roll = random.randint(1, 20)
        result = SONS.get(roll, "Inconnu")
        return jsonify({"roll": roll, "result": result})
    elif table == "EFFET_DE_SORT":
        roll = random.randint(1, 20)
        result = EFFET_DE_SORT.get(roll, "Inconnu")
        return jsonify({"roll": roll, "result": result})
    elif table == "DESCRIPTEUR_VAISSEAU_SPATIAL":
        roll = random.randint(1, 20)
        result = DESCRIPTEUR_VAISSEAU_SPATIAL.get(roll, "Inconnu")
        return jsonify({"roll": roll, "result": result})
    elif table == "DESCRIPTEUR_TERRAIN":
        roll = random.randint(1, 20)
        result = DESCRIPTEUR_TERRAIN.get(roll, "Inconnu")
        return jsonify({"roll": roll, "result": result})    
    elif table == "DESCRIPTEUR_MORT_VIVANT":
        roll = random.randint(1, 20)
        result = DESCRIPTEUR_MORT_VIVANT.get(roll, "Inconnu")
        return jsonify({"roll": roll, "result": result})
    else:
        return jsonify({"error": "Table non définie"})

@app.route("/add_custom_table", methods=["POST"])
@auth.login_required
def add_custom_table():
    name = request.form.get("customTableName").strip()
    values = request.form.get("customTableValues").strip()
    if name and values:
        new_table = CustomTable(name=name, values=values)
        db.session.add(new_table)
        db.session.commit()
    return jsonify({"success": True}), 200

@app.route("/delete_custom_table/<int:table_id>", methods=["POST"])
@auth.login_required
def delete_custom_table(table_id):
    table = CustomTable.query.get_or_404(table_id)
    db.session.delete(table)
    db.session.commit()
    return jsonify({"success": True}), 200

@app.route("/edit_custom_table/<int:table_id>", methods=["POST"])
@auth.login_required
def edit_custom_table(table_id):
    print('edit !')
    table = CustomTable.query.get_or_404(table_id)
    table.name = request.form.get("customTableNameEdit").strip()
    table.values = request.form.get("customTableValuesEdit").strip()
    db.session.commit()
    return jsonify({"success": True}), 200

@app.route("/get_custom_table", methods=["POST"])
@auth.login_required
def get_custom_table():
    table_id = request.args.get("table_id")
    table = CustomTable.query.get(table_id)
    if table:
        return jsonify({"values": table.values})
    else:
        return jsonify({"error": "Table non trouvée"})

@app.route("/add_player", methods=["POST"])
@auth.login_required
def add_player():
    name = request.form.get("name").strip()
    description = request.form.get("description").strip()
    if name:
        new_player = PlayerCharacter(name=name, description=description)
        db.session.add(new_player)
        db.session.commit()
    return jsonify({"success": True}), 200

@app.route("/delete_player/<int:player_id>", methods=["POST"])
@auth.login_required
def delete_player(player_id):
    print('elete')
    player = PlayerCharacter.query.get_or_404(player_id)
    db.session.delete(player)
    db.session.commit()
    return jsonify({"success": True}), 200

@app.route("/add_player_attribute/<int:player_id>", methods=["POST"])
@auth.login_required
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
    return jsonify({"success": True}), 200

@app.route("/delete_player_attribute/<int:attribute_id>", methods=["POST"])
@auth.login_required
def delete_player_attribute(attribute_id):
    attribute = PlayerAttribute.query.get_or_404(attribute_id)
    db.session.delete(attribute)
    db.session.commit()
    return jsonify({"success": True}), 200

@app.route("/edit_player_description/<int:player_id>", methods=["POST"])
@auth.login_required
def edit_player_description(player_id):
    player = PlayerCharacter.query.get_or_404(player_id)
    player.description = request.form.get("description").strip()
    db.session.commit()
    return jsonify({"success": True}), 200

@app.route("/update_chaos", methods=["POST"])
@auth.login_required
def update_chaos():
    adjustment = int(request.form.get("adjustment"))
    game_state = GameState.query.first()
    game_state.chaos_factor = max(1, min(9, game_state.chaos_factor + adjustment))
    db.session.commit()
    return jsonify({"new_chaos": game_state.chaos_factor})

@app.route("/roll_dice/<int:faces>", methods=["POST"])
@auth.login_required
def roll_dice(faces):
    if faces < 1:
        return jsonify({"error": "Nombre de faces invalide"}), 400
    roll = random.randint(1, faces)
    # Sauvegarder le lancer dans la base SQL
    new_roll = DiceRollHistory(faces=faces, roll=roll)
    db.session.add(new_roll)
    db.session.commit()
    return jsonify({"roll": roll, "faces": faces})

@app.route("/dice_history", methods=["POST"])
@auth.login_required
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
    app.run(debug=False, port=5345)
