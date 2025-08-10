import random
import time

def start_game_mode(user_id, mode, db):
    """
    Simulate a game session based on the mode.
    Returns a result dict with earnings, status, and details.
    """

    # Example simplified game result data, you need to expand this based on your modes and rules
    base_earning = random.randint(8, 12)
    max_earning = 50
    gold_earned = min(base_earning + random.randint(0, 10), max_earning)
    diamonds_earned = 0

    if mode == "rage":
        # Example logic for rage mode diamond earning
        kills = random.randint(0, 3)
        diamonds_earned = kills // 2  # 1 diamond per 2 kills

    # Update honor score logic could be added here

    return {
        "gold": gold_earned,
        "diamonds": diamonds_earned,
        "mode": mode,
        "result": "win" if gold_earned > 0 else "lose",
        "kills": diamonds_earned * 2 if mode == "rage" else 0,
        "hits": gold_earned if mode == "offensive" else 0,
    }
