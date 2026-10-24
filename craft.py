"""Крафт. Здесь пишем новую систему.

Рецепты и вместимость инвентаря лежат в recipes.py, их трогать нельзя.
Правила и контракт описаны в README.
"""
import random

from recipes import CAPACITY, RECIPES


def craft(inventory, recipe_name, player_level):
    """Скрафтить предмет по рецепту recipe_name.

    Если крафт не удался, инвентарь не меняется вообще. Если крафт невозможен,
    кидаем ValueError. Если всё получилось, возвращаем новый предмет.
    """
    if recipe_name not in RECIPES:
        raise ValueError("нет такого рецепта: " + recipe_name)
    recipe = RECIPES[recipe_name]

    if type(player_level) is not int or player_level < 1:
        raise ValueError("уровень игрока должен быть целым числом от 1")
    if player_level < recipe["level"]:
        raise ValueError("уровень мал для рецепта")

    spent = []
    for name, need in recipe["ingredients"].items():
        indexes = [
            i for i, thing in enumerate(inventory)
            if thing["name"] == name and not thing.get("equipped", False)
        ]
        if len(indexes) < need:
            raise ValueError("не хватает ингредиента: " + name)
        indexes.sort(key=lambda i: (-inventory[i]["quality"], i))
        spent.extend(indexes[:need])

    if len(inventory) >= CAPACITY:
        raise ValueError("нет свободной ячейки в инвентаре")

    if random.random() < recipe["fail_chance"]:
        return None

    taken = [inventory[i] for i in spent]
    result = {"name": recipe_name, "quality": min(t["quality"] for t in taken)}

    removed = set(spent)
    inventory[:] = [t for i, t in enumerate(inventory) if i not in removed] + [result]
    return result
