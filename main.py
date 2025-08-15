import os
import discord
from discord.ext import commands
import random
import asyncio
import json
import logging
from datetime import datetime, timedelta
from dotenv import load_dotenv

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Load env variables
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
OWNER_ID = int(os.getenv("OWNER_ID", "0"))

if not TOKEN:
    logger.error("DISCORD_TOKEN not found in environment variables")
    exit(1)

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

# === Données utilisateurs ===
try:
    with open("users.json", "r") as f:
        users = json.load(f)
    logger.info("User data loaded successfully")
except FileNotFoundError:
    users = {}
    logger.info("No existing user data found, starting fresh")
except json.JSONDecodeError:
    logger.error("Corrupted user data file, starting fresh")
    users = {}

# === Boutique ===
shop_items = {
    "role_vip": {"prix": 1000, "description": "Un rôle VIP spécial."},
    "ticket_loterie": {"prix": 250, "description": "Un ticket pour une future loterie."},
    "boost_x2": {"prix": 1200, "description": "Double tes gains pendant 1h."},
    "emoji_special": {"prix": 300, "description": "Débloque un emoji spécial du serveur."},
    "badge": {"prix": 500, "description": "Badge de joueur régulier."},
    "boost_x3": {"prix": 2000, "description": "Triple tes gains pendant 1h."},
    "skin_slot": {"prix": 900, "description": "Change l'apparence du slot."},
    "extra_steal": {"prix": 1500, "description": "Permet un vol supplémentaire par jour."}
}

# === Fonctions utilitaires ===
def save_users():
    """Save user data to JSON file with error handling"""
    try:
        with open("users.json", "w") as f:
            json.dump(users, f, indent=2)
        logger.info("User data saved successfully")
    except Exception as e:
        logger.error(f"Failed to save user data: {e}")

def get_user_data(user_id):
    """Get user data, create if doesn't exist"""
    user_id_str = str(user_id)
    if user_id_str not in users:
        users[user_id_str] = {
            "balance": 500,
            "last_daily": "",
            "steals": [],
            "items": [],
            "boost_end": None,
            "games_played": 0,
            "total_winnings": 0,
            "total_losses": 0
        }
        logger.info(f"Created new user data for {user_id}")
    return users[user_id_str]

def has_boost(user):
    """Check if user has an active boost"""
    boost_end = user.get("boost_end")
    if boost_end:
        try:
            boost_end_dt = datetime.fromisoformat(boost_end)
            return datetime.utcnow() < boost_end_dt
        except ValueError:
            logger.warning(f"Invalid boost_end format: {boost_end}")
            return False
    return False

def get_boost_multiplier(user):
    """Get the boost multiplier for a user"""
    if not has_boost(user):
        return 1

    if "boost_x3" in user["items"]:
        return 3
    elif "boost_x2" in user["items"]:
        return 2
    return 1

def apply_boost(montant, user):
    """Apply boost multiplier to amount"""
    multiplier = get_boost_multiplier(user)
    return montant * multiplier

def reset_steals_if_needed(user):
    """Clean up steal list if day has changed"""
    today = str(datetime.utcnow().date())
    user["steals"] = [s for s in user.get("steals", []) if s == today]
    return user

def validate_bet(ctx, user, mise):
    """Validate if bet is valid"""
    if mise <= 0:
        return False, "❌ La mise doit être positive."
    if mise > user["balance"]:
        return False, "❌ Tu n'as pas assez de pièces pour cette mise."
    return True, ""

def record_game_result(user, mise, gain):
    """Record game statistics"""
    user["games_played"] += 1
    if gain > mise:
        user["total_winnings"] += (gain - mise)
    else:
        user["total_losses"] += mise

# === Event handlers ===
@bot.event
async def on_ready():
    logger.info(f"{bot.user} est prêt!")
    print(f"{bot.user} est prêt!")
    try:
        synced = await bot.tree.sync()
        logger.info(f"Synced {len(synced)} command(s)")
    except Exception as e:
        logger.error(f"Failed to sync commands: {e}")

@bot.event
async def on_command_error(ctx, error):
    """Global error handler"""
    if isinstance(error, commands.CommandNotFound):
        await ctx.send("❌ Commande non trouvée. Utilise `!aide` pour voir les commandes disponibles.")
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(f"❌ Argument manquant. Utilise `!aide` pour voir la syntaxe correcte.")
    elif isinstance(error, commands.BadArgument):
        await ctx.send("❌ Argument invalide. Vérifie tes paramètres.")
    elif isinstance(error, commands.NotOwner):
        await ctx.send("❌ Cette commande est réservée au propriétaire du bot.")
    else:
        logger.error(f"Unhandled error in {ctx.command}: {error}")
        await ctx.send("❌ Une erreur inattendue s'est produite.")

# === Commandes ===

@bot.command()
async def aide(ctx):
    """Display help information"""
    embed = discord.Embed(title="🎰 Aide du Casino Bot", color=discord.Color.gold())
    embed.add_field(name="!daily", value="Réclame ta récompense quotidienne (100 pièces, boost possible).", inline=False)
    embed.add_field(name="!balance", value="Affiche ton solde.", inline=False)
    embed.add_field(name="!coinflip <mise>", value="Joue à pile ou face.", inline=False)
    embed.add_field(name="!dice <mise>", value="Lance un dé contre le bot.", inline=False)
    embed.add_field(name="!roulette <mise> <couleur>", value="Parie sur rouge, noir ou vert.", inline=False)
    embed.add_field(name="!blackjack <mise>", value="Joue au blackjack contre le bot.", inline=False)
    embed.add_field(name="!slot <mise>", value="Joue au bandit manchot.", inline=False)
    embed.add_field(name="!steal <@utilisateur>", value="Vole un autre joueur (3 fois max par jour, boost pour extra steal).", inline=False)
    embed.add_field(name="!boutique", value="Affiche les objets disponibles à l'achat.", inline=False)
    embed.add_field(name="!acheter <objet>", value="Achète un objet de la boutique.", inline=False)
    embed.add_field(name="!profil", value="Montre ton profil complet.", inline=False)
    embed.add_field(name="!don", value="Don a un Joueur.", inline=False)

    if ctx.author.id == OWNER_ID:
        embed.add_field(name="!give <@user> <montant>", value="(Owner) Donne de l'argent à un joueur.", inline=False)
        embed.add_field(name="!remove <@user> <montant>", value="(Owner) Retire de l'argent à un joueur.", inline=False)
    await ctx.send(embed=embed)

@bot.command()
async def daily(ctx):
    """Daily reward command"""
    user = get_user_data(ctx.author.id)
    now = datetime.utcnow()
    last_daily_str = user.get("last_daily", "")

    if last_daily_str:
        try:
            last_daily = datetime.fromisoformat(last_daily_str)
            if now - last_daily < timedelta(hours=24):
                reste = timedelta(hours=24) - (now - last_daily)
                heures = int(reste.total_seconds() // 3600)
                minutes = int((reste.total_seconds() % 3600) // 60)
                await ctx.send(f"⏳ Tu as déjà pris ta récompense quotidienne. Reviens dans {heures}h {minutes}m.")
                return
        except ValueError:
            logger.warning(f"Invalid last_daily format for user {ctx.author.id}: {last_daily_str}")

    base_gain = 100
    gain = apply_boost(base_gain, user)
    user["balance"] += gain
    user["last_daily"] = now.isoformat()
    save_users()

    embed = discord.Embed(title="🎁 Récompense quotidienne", description=f"Tu as reçu **{gain}** pièces !", color=discord.Color.green())
    if gain > base_gain:
        embed.add_field(name="🚀 Boost actif!", value=f"Multiplier x{gain//base_gain}", inline=False)
    embed.set_thumbnail(url=str(ctx.author.display_avatar))
    await ctx.send(embed=embed)

@bot.command()
async def balance(ctx):
    """Display user balance"""
    user = get_user_data(ctx.author.id)
    embed = discord.Embed(title=f"💰 Solde de {ctx.author.display_name}", color=discord.Color.gold())
    embed.add_field(name="Pièces", value=f"{user['balance']:,}", inline=False)
    embed.set_thumbnail(url=str(ctx.author.display_avatar))
    await ctx.send(embed=embed)

@bot.command()
async def boutique(ctx):
    """Display shop items"""
    embed = discord.Embed(title="🛒 Boutique du Casino", color=discord.Color.blue())
    for item, info in shop_items.items():
        embed.add_field(name=f"{item} - {info['prix']:,} pièces", value=info['description'], inline=False)
    await ctx.send(embed=embed)

@bot.command()
async def acheter(ctx, *, objet: str):
    """Buy shop item"""
    user = get_user_data(ctx.author.id)
    objet = objet.lower().replace(" ", "_")

    if objet not in shop_items:
        available_items = ", ".join(shop_items.keys())
        await ctx.send(f"❌ Cet objet n'existe pas. Objets disponibles: {available_items}")
        return

    prix = shop_items[objet]['prix']
    if user['balance'] < prix:
        await ctx.send(f"❌ Tu n'as pas assez de pièces pour acheter ça. Il te faut {prix:,} pièces.")
        return

    if objet in user['items']:
        await ctx.send("📦 Tu possèdes déjà cet objet.")
        return

    user['balance'] -= prix
    user['items'].append(objet)

    if "boost" in objet:
        # boost lasts 1 hour from purchase time
        expire = datetime.utcnow() + timedelta(hours=1)
        user["boost_end"] = expire.isoformat()

    save_users()
    await ctx.send(f"✅ Tu as acheté **{objet}** pour {prix:,} pièces !")

@bot.command()
async def profil(ctx, member: discord.Member = None):
    """Display user profile"""
    if not member:
        member = ctx.author
    user = get_user_data(member.id)

    # Créateur : affichage spécial
    if member.id == OWNER_ID:
        embed = discord.Embed(
            title=f"👑 Créateur est Roi: {member.display_name}",
            color=discord.Color.gold()
        )
        embed.add_field(name="Rôle", value="Créateur du bot", inline=True)
    else:
        embed = discord.Embed(
            title=f"👤 Profil de {member.display_name}",
            color=discord.Color.teal()
        )

    embed.set_thumbnail(url=str(member.display_avatar))
    embed.add_field(name="Pièces", value=f"{user['balance']:,}", inline=True)
    embed.add_field(name="Objets", value=", ".join(user["items"]) if user["items"] else "Aucun", inline=True)
    boost_status = "Actif" if has_boost(user) else "Inactif"
    embed.add_field(name="Boost", value=boost_status, inline=True)
    embed.add_field(name="Vols aujourd'hui", value=str(len(user.get("steals", []))), inline=True)
    embed.add_field(name="Parties jouées", value=str(user.get("games_played", 0)), inline=True)
    embed.add_field(name="Gains totaux", value=f"{user.get('total_winnings', 0):,}", inline=True)
    embed.add_field(name="Pertes totales", value=f"{user.get('total_losses', 0):,}", inline=True)

    await ctx.send(embed=embed)

@bot.command()
async def classement(ctx):
    """Display leaderboard"""
    # Sort by balance descending, excluding owner
    ranking = sorted(
        [(uid, data) for uid, data in users.items() if int(uid) != OWNER_ID and data.get('balance', 0) > 0],
        key=lambda x: x[1]["balance"],
        reverse=True
    )

    embed = discord.Embed(title="🏆 Top 10 joueurs", color=discord.Color.gold())
    for i, (uid, data) in enumerate(ranking[:10], start=1):
        try:
            user = await bot.fetch_user(int(uid))
            embed.add_field(name=f"{i}. {user.display_name}", value=f"{data['balance']:,} pièces", inline=False)
        except discord.NotFound:
            embed.add_field(name=f"{i}. Utilisateur inconnu", value=f"{data['balance']:,} pièces", inline=False)

    if not ranking:
        embed.add_field(name="Aucun joueur", value="Sois le premier à jouer!", inline=False)

    await ctx.send(embed=embed)

@bot.command()
async def steal(ctx, cible: discord.Member):
    """Steal from another user"""
    if cible.bot or cible.id == ctx.author.id:
        await ctx.send("❌ Tu ne peux pas voler ce joueur.")
        return

    user = get_user_data(ctx.author.id)
    cible_user = get_user_data(cible.id)

    # Reset steals if needed
    user = reset_steals_if_needed(user)

    now = datetime.utcnow()
    today_str = str(now.date())
    steals_today = user.get("steals", [])

    max_steals = 3
    if "extra_steal" in user["items"]:
        max_steals = 4

    if len(steals_today) >= max_steals:
        await ctx.send(f"❌ Tu as atteint ta limite de vols aujourd'hui ({max_steals}).")
        return

    if cible_user["balance"] < 50:
        await ctx.send("❌ Cette personne n'a pas assez de pièces pour être volée (minimum 50).")
        return

    # Success rate is 70%
    if random.random() > 0.7:
        await ctx.send(f"❌ Ton vol a échoué! {cible.display_name} t'a attrapé!")
        steals_today.append(today_str)
        user["steals"] = steals_today
        save_users()
        return

    gain = random.randint(20, min(100, cible_user["balance"] // 2))
    cible_user["balance"] -= gain
    user["balance"] += gain
    steals_today.append(today_str)
    user["steals"] = steals_today
    save_users()

    embed = discord.Embed(title="🦹‍♂️ Vol réussi", color=discord.Color.dark_red())
    embed.add_field(name=f"{ctx.author.display_name} a volé {cible.display_name}", value=f"Gain : {gain:,} pièces", inline=False)
    embed.set_thumbnail(url=str(ctx.author.display_avatar))
    await ctx.send(embed=embed)

# === Owner Commands ===
@bot.command()
@commands.is_owner()
async def give(ctx, member: discord.Member, amount: int):
    """Give money to a user (owner only)"""
    user = get_user_data(member.id)
    user["balance"] += amount
    save_users()
    await ctx.send(f"✅ {amount:,} pièces ajoutées à {member.display_name}.")

@bot.command()
@commands.is_owner()
async def remove(ctx, member: discord.Member, amount: int):
    """Remove money from a user (owner only)"""
    user = get_user_data(member.id)
    user["balance"] = max(user["balance"] - amount, 0)
    save_users()
    await ctx.send(f"✅ {amount:,} pièces retirées de {member.display_name}.")

# === Utility function for animated results ===
async def wait_and_send(ctx, result_embed, gif_url, duration=3):
    """Display gif then result"""
    gif_embed = discord.Embed(color=discord.Color.gold())
    gif_embed.set_image(url=gif_url)
    gif_embed.set_footer(text="🎲 Jeu en cours...")

    msg = await ctx.send(embed=gif_embed)
    await asyncio.sleep(duration)
    await msg.edit(embed=result_embed)

    
    # Commande des jeux avec cooldown de 3 secondes par utilisateur
    @bot.command()
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def jouer(ctx, jeu: str, mise: int):
        jeu = jeu.lower()

        if jeu == "coinflip":
            await coinflip.callback(ctx, mise)
        elif jeu == "dice":
            await dice.callback(ctx, mise)
        elif jeu == "roulette":
            await roulette.callback(ctx, mise)
        elif jeu == "blackjack":
            await blackjack.callback(ctx, mise)
        elif jeu == "slot":
            await slot.callback(ctx, mise)
        else:
            embed = discord.Embed(
                title="❌ Jeu inconnu",
                description="Utilise : coinflip, dice, roulette, blackjack, slot.",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)

    # Gestion des erreurs, notamment le cooldown
    @jouer.error
    async def jouer_error(ctx, error):
        if isinstance(error, commands.CommandOnCooldown):
            embed = discord.Embed(
                title="⏳ Cooldown",
                description=f"Patiente **{error.retry_after:.1f} secondes** avant de rejouer !",
                color=discord.Color.orange()
            )
            await ctx.send(embed=embed)
        else:
            embed = discord.Embed(
                title="❌ Erreur",
                description="Une erreur est survenue.",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)


# === Gambling Games ===

@bot.command()
async def coinflip(ctx, mise: int):
    """Coinflip game - 50/50 chance"""
    user = get_user_data(ctx.author.id)

    # Validate bet
    valid, error_msg = validate_bet(ctx, user, mise)
    if not valid:
        await ctx.send(error_msg)
        return

    user["balance"] -= mise

    # Game logic
    player_choice = random.choice(["pile", "face"])
    bot_choice = random.choice(["pile", "face"])

    # Create result embed
    embed = discord.Embed(title="🪙 Pile ou Face", color=discord.Color.gold())
    embed.add_field(name="Ton choix", value=player_choice.capitalize(), inline=True)
    embed.add_field(name="Résultat", value=bot_choice.capitalize(), inline=True)

    if player_choice == bot_choice:
        # Win - double the bet
        gain = apply_boost(mise * 2, user)
        user["balance"] += gain
        record_game_result(user, mise, gain)

        embed.color = discord.Color.green()
        embed.add_field(name="🎉 Résultat", value=f"Gagné! +{gain:,} pièces", inline=False)
        if gain > mise * 2:
            embed.add_field(name="🚀 Boost actif!", value=f"Gains multipliés!", inline=False)
    else:
        # Lose
        record_game_result(user, mise, 0)
        embed.color = discord.Color.red()
        embed.add_field(name="😢 Résultat", value=f"Perdu! -{mise:,} pièces", inline=False)

    save_users()

    # Animated result
    gif_url = "https://media.giphy.com/media/YrD1PQldGsstG/giphy.gif"
    await wait_and_send(ctx, embed, gif_url)

@bot.command()
async def dice(ctx, mise: int):
    """Dice game - roll higher than bot"""
    user = get_user_data(ctx.author.id)

    # Validate bet
    valid, error_msg = validate_bet(ctx, user, mise)
    if not valid:
        await ctx.send(error_msg)
        return

    user["balance"] -= mise

    # Game logic
    player_roll = random.randint(1, 6)
    bot_roll = random.randint(1, 6)

    # Create result embed
    embed = discord.Embed(title="🎲 Bataille de Dés", color=discord.Color.blue())
    embed.add_field(name="Ton dé", value=f"🎲 {player_roll}", inline=True)
    embed.add_field(name="Dé du bot", value=f"🎲 {bot_roll}", inline=True)

    if player_roll > bot_roll:
        # Win - 1.8x multiplier
        gain = apply_boost(int(mise * 1.8), user)
        user["balance"] += gain
        record_game_result(user, mise, gain)

        embed.color = discord.Color.green()
        embed.add_field(name="🎉 Résultat", value=f"Victoire! +{gain:,} pièces", inline=False)
    elif player_roll == bot_roll:
        # Tie - return bet
        user["balance"] += mise
        record_game_result(user, mise, mise)

        embed.color = discord.Color.gold()
        embed.add_field(name="🤝 Résultat", value="Égalité! Mise remboursée", inline=False)
    else:
        # Lose
        record_game_result(user, mise, 0)
        embed.color = discord.Color.red()
        embed.add_field(name="😢 Résultat", value=f"Défaite! -{mise:,} pièces", inline=False)

    save_users()

    # Animated result
    gif_url = "https://media.giphy.com/media/l0HlL6eH6eEqCzoCc/giphy.gif"
    await wait_and_send(ctx, embed, gif_url)

@bot.command()
async def roulette(ctx, mise: int, couleur: str):
    """Roulette game"""
    couleur = couleur.lower()
    if couleur not in ["rouge", "noir", "vert"]:
        await ctx.send("❌ Couleur invalide. Choisis rouge, noir ou vert.")
        return

    user = get_user_data(ctx.author.id)

    # Validate bet
    valid, error_msg = validate_bet(ctx, user, mise)
    if not valid:
        await ctx.send(error_msg)
        return

    user["balance"] -= mise

    # Game logic - European roulette odds
    resultats = ["rouge"] * 18 + ["noir"] * 18 + ["vert"] * 1
    resultat = random.choice(resultats)

    # Create result embed
    embed = discord.Embed(title="🎡 Roulette", color=discord.Color.purple())
    embed.add_field(name="Ton pari", value=couleur.capitalize(), inline=True)
    embed.add_field(name="Résultat", value=resultat.capitalize(), inline=True)

    if couleur == resultat:
        # Win
        if couleur == "vert":
            gain = apply_boost(mise * 35, user)  # 35:1 for green
        else:
            gain = apply_boost(mise * 2, user)  # 2:1 for red/black

        user["balance"] += gain
        record_game_result(user, mise, gain)

        embed.color = discord.Color.green()
        embed.add_field(name="🎉 Résultat", value=f"Gagné! +{gain:,} pièces", inline=False)
    else:
        # Lose
        record_game_result(user, mise, 0)
        embed.color = discord.Color.red()
        embed.add_field(name="😢 Résultat", value=f"Perdu! -{mise:,} pièces", inline=False)

    save_users()

    # Animated result
    gif_url = "https://media.giphy.com/media/YWb4A6K4SQUq4/giphy.gif"
    await wait_and_send(ctx, embed, gif_url)

@bot.command()
async def blackjack(ctx, mise: int):
    """Simplified blackjack game"""
    user = get_user_data(ctx.author.id)

    # Validate bet
    valid, error_msg = validate_bet(ctx, user, mise)
    if not valid:
        await ctx.send(error_msg)
        return

    user["balance"] -= mise

    # Simplified blackjack logic
    def get_card_value():
        return random.randint(1, 11)

    def get_hand_value(cards):
        total = sum(cards)
        # Simple ace handling
        aces = cards.count(11)
        while total > 21 and aces > 0:
            total -= 10
            aces -= 1
        return total

    # Deal initial cards
    player_cards = [get_card_value(), get_card_value()]
    dealer_cards = [get_card_value(), get_card_value()]

    player_total = get_hand_value(player_cards)
    dealer_total = get_hand_value(dealer_cards)

    # Dealer hits until 17 or bust
    while dealer_total < 17:
        dealer_cards.append(get_card_value())
        dealer_total = get_hand_value(dealer_cards)

    # Create result embed
    embed = discord.Embed(title="🃏 Blackjack", color=discord.Color.dark_green())
    embed.add_field(name="Tes cartes", value=f"Total: {player_total}", inline=True)
    embed.add_field(name="Cartes du dealer", value=f"Total: {dealer_total}", inline=True)

    # Determine winner
    if player_total > 21:
        # Player bust
        record_game_result(user, mise, 0)
        embed.color = discord.Color.red()
        embed.add_field(name="😢 Résultat", value=f"Bust! Perdu -{mise:,} pièces", inline=False)
    elif dealer_total > 21:
        # Dealer bust - player wins
        gain = apply_boost(mise * 2, user)
        user["balance"] += gain
        record_game_result(user, mise, gain)
        embed.color = discord.Color.green()
        embed.add_field(name="🎉 Résultat", value=f"Dealer bust! +{gain:,} pièces", inline=False)
    elif player_total > dealer_total:
        # Player wins
        gain = apply_boost(mise * 2, user)
        user["balance"] += gain
        record_game_result(user, mise, gain)
        embed.color = discord.Color.green()
        embed.add_field(name="🎉 Résultat", value=f"Victoire! +{gain:,} pièces", inline=False)
    elif player_total == dealer_total:
        # Tie - return bet
        user["balance"] += mise
        record_game_result(user, mise, mise)
        embed.color = discord.Color.gold()
        embed.add_field(name="🤝 Résultat", value="Égalité! Mise remboursée", inline=False)
    else:
        # Dealer wins
        record_game_result(user, mise, 0)
        embed.color = discord.Color.red()
        embed.add_field(name="😢 Résultat", value=f"Défaite! -{mise:,} pièces", inline=False)

    save_users()

    # Animated result
    gif_url = "https://media.giphy.com/media/l0HlL6eH6eEqCzoCc/giphy.gif"
    await wait_and_send(ctx, embed, gif_url)

@bot.command()
async def slot(ctx, mise: int):
    """Slot machine game"""
    user = get_user_data(ctx.author.id)

    # Validate bet
    valid, error_msg = validate_bet(ctx, user, mise)
    if not valid:
        await ctx.send(error_msg)
        return

    user["balance"] -= mise

    # Slot machine symbols with weights
    symbols = ["🍎", "🍊", "🍋", "🍇", "🍒", "💎", "⭐", "7️⃣"]
    weights = [20, 20, 20, 15, 15, 5, 3, 2]  # Diamond, star, and 7 are rarer

    # Spin the reels
    reel1 = random.choices(symbols, weights=weights)[0]
    reel2 = random.choices(symbols, weights=weights)[0]
    reel3 = random.choices(symbols, weights=weights)[0]

    # Determine payout
    if reel1 == reel2 == reel3:
        # Three of a kind
        if reel1 == "7️⃣":
            multiplier = 50  # Jackpot!
        elif reel1 == "⭐":
            multiplier = 25
        elif reel1 == "💎":
            multiplier = 15
        elif reel1 == "🍒":
            multiplier = 10
        else:
            multiplier = 5
    elif reel1 == reel2 or reel2 == reel3 or reel1 == reel3:
        # Two of a kind
        multiplier = 2
    else:
        # No match
        multiplier = 0

    # Apply skin if user has it
    skin_prefix = "✨" if "skin_slot" in user["items"] else ""

    # Create result embed
    embed = discord.Embed(title="🎰 Machine à Sous", color=discord.Color.purple())
    embed.add_field(name="Résultat", value=f"{skin_prefix}{reel1} {reel2} {reel3}{skin_prefix}", inline=False)

    if multiplier > 0:
        gain = apply_boost(mise * multiplier, user)
        user["balance"] += gain
        record_game_result(user, mise, gain)

        embed.color = discord.Color.green()
        if multiplier >= 50:
            embed.add_field(name="🎉 JACKPOT! 🎉", value=f"Incroyable! +{gain:,} pièces", inline=False)
        elif multiplier >= 10:
            embed.add_field(name="🌟 GROS GAIN!", value=f"Excellent! +{gain:,} pièces", inline=False)
        else:
            embed.add_field(name="🎉 Gagné!", value=f"+{gain:,} pièces", inline=False)
    else:
        record_game_result(user, mise, 0)
        embed.color = discord.Color.red()
        embed.add_field(name="😢 Perdu", value=f"Pas de chance! -{mise:,} pièces", inline=False)

    save_users()

    # Animated result
    gif_url = "https://media.giphy.com/media/l0HlKV3UlKNgNXVyE/giphy.gif"
    await wait_and_send(ctx, embed, gif_url)

# === Statistics command ===
@bot.command()
async def stats(ctx):
    """Display bot statistics"""
    total_users = len(users)
    total_balance = sum(user.get('balance', 0) for user in users.values())
    total_games = sum(user.get('games_played', 0) for user in users.values())

    embed = discord.Embed(title="📊 Statistiques du Casino", color=discord.Color.blue())
    embed.add_field(name="Joueurs totaux", value=str(total_users), inline=True)
    embed.add_field(name="Pièces en circulation", value=f"{total_balance:,}", inline=True)
    embed.add_field(name="Parties jouées", value=str(total_games), inline=True)
    embed.add_field(name="Serveurs", value=str(len(bot.guilds)), inline=True)

    await ctx.send(embed=embed)

@bot.command()
async def don(ctx, membre: discord.Member, montant: int):
    """Donner des pièces à un autre joueur"""
    donneur = get_user_data(ctx.author.id)
    receveur = get_user_data(membre.id)

    # Vérification basique
    if membre.bot:
        await ctx.send("❌ Tu ne peux pas donner des pièces à un bot.")
        return
    if membre.id == ctx.author.id:
        await ctx.send("❌ Tu ne peux pas te donner des pièces à toi-même.")
        return
    if montant <= 0:
        await ctx.send("❌ Le montant doit être positif.")
        return
    if donneur["balance"] < montant:
        await ctx.send("❌ Tu n'as pas assez de pièces pour ce don.")
        return

    # Transfert
    donneur["balance"] -= montant
    receveur["balance"] += montant
    save_users()

    embed = discord.Embed(
        title="🤝 Don de pièces",
        description=f"**{ctx.author.display_name}** a donné **{montant:,}** pièces à **{membre.display_name}**.",
        color=discord.Color.green()
    )
    embed.set_thumbnail(url=str(ctx.author.display_avatar))
    await ctx.send(embed=embed)

# Run the bot
if __name__ == "__main__":
    try:
        bot.run(TOKEN)
    except Exception as e:
        logger.error(f"Failed to start bot: {e}")

