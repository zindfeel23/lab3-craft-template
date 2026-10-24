"""Тесты для крафта.

Все тесты берут реализацию из фикстуры impl, поэтому их можно гонять и на
моём craft.py, и на крафте Валеры, и на эталонных реализациях автопроверки.
"""
import types
from contextlib import ExitStack
from unittest.mock import patch

import pytest

from recipes import CAPACITY


def item(name, quality=3, equipped=False):
    thing = {"name": name, "quality": quality}
    if equipped:
        thing["equipped"] = True
    return thing


def patch_dice(impl, **kwargs):
    """Подменить кубик, не зная, как именно его импортировал impl.

    Одна реализация пишет import random и зовёт random.random(), другая
    from random import random и зовёт random(). Патчим оба места сразу.
    """
    stack = ExitStack()
    stack.enter_context(patch("random.random", **kwargs))
    own = getattr(impl, "random", None)
    if own is not None and not isinstance(own, types.ModuleType):
        stack.enter_context(patch.object(impl, "random", **kwargs))
    return stack


# --- пункт 1: атомарный крафт по правилам ---

def test_torch(impl):
    """Пример из условия. У факела шанс провала 0.0, кубик можно не трогать."""
    inventory = [item("палка", 2), item("смола", 4), item("кожа")]
    torch = impl.craft(inventory, "факел", 1)
    assert torch == {"name": "факел", "quality": 2}
    assert inventory == [item("кожа"), torch]


def test_happy_path_sword(impl):
    """Обычный успех: ингредиенты списаны, результат в конце, порядок сохранён."""
    inventory = [item("сталь", 5), item("сталь", 2), item("дерево", 4), item("кожа", 3)]
    with patch_dice(impl, return_value=1.0):
        result = impl.craft(inventory, "меч", 10)
    assert result == {"name": "меч", "quality": 2}
    assert inventory == [item("кожа", 3), result]


def test_not_enough_ingredient(impl):
    """Для меча нужно две стали, а она одна. Отказ, инвентарь не тронут."""
    inventory = [item("сталь", 3), item("дерево", 4)]
    with pytest.raises(ValueError):
        impl.craft(inventory, "меч", 10)
    assert inventory == [item("сталь", 3), item("дерево", 4)]


def test_empty_inventory(impl):
    inventory = []
    with pytest.raises(ValueError):
        impl.craft(inventory, "факел", 1)
    assert inventory == []


def test_exactly_enough(impl):
    """Ингредиентов ровно столько, сколько нужно."""
    inventory = [item("доска", 2), item("доска", 3), item("доска", 4), item("кожа", 5)]
    with patch_dice(impl, return_value=1.0):
        result = impl.craft(inventory, "щит", 3)
    assert result == {"name": "щит", "quality": 2}
    assert inventory == [result]


def test_atomic_on_fail(impl):
    """Крафт не удался, инвентарь остался в точности как был."""
    inventory = [item("сталь", 3), item("сталь", 2), item("дерево", 4)]
    before = list(inventory)
    with patch_dice(impl, return_value=0.0):
        result = impl.craft(inventory, "меч", 10)
    assert result is None
    assert inventory == before
    assert len(inventory) == len(before)
    assert all(a is b for a, b in zip(inventory, before))


# --- пункт 2: тесты, которые валят реализацию Валеры ---

def test_missing_first_ingredient(impl):
    """Мечу не хватает стали (первый ингредиент), дерево на месте.

    У Валеры все лямбды смотрят на последний ингредиент, проверка пропускает
    нехватку стали, а потом _take списывает одну сталь и падает посередине.
    """
    inventory = [item("сталь", 3), item("дерево", 4)]
    with pytest.raises(ValueError):
        impl.craft(inventory, "меч", 10)
    assert inventory == [item("сталь", 3), item("дерево", 4)]


def test_fail_keeps_inventory(impl):
    """Провал на кубике. Валера списывает ингредиенты до кубика, у нас нет."""
    inventory = [item("сталь", 5), item("сталь", 2), item("дерево", 4)]
    before = list(inventory)
    with patch_dice(impl, return_value=0.0):
        result = impl.craft(inventory, "меч", 10)
    assert result is None
    assert inventory == before


def test_spends_best_quality(impl):
    """Списываются лучшие по качеству. Валера берёт первый попавшийся."""
    inventory = [item("палка", 2), item("палка", 5), item("смола", 3)]
    result = impl.craft(inventory, "факел", 1)
    assert result == {"name": "факел", "quality": 3}
    assert inventory == [item("палка", 2), result]


# --- пункт 3: детерминированный кубик ---

def test_dice_below_fail_chance_fails(impl):
    """0.0 меньше любого шанса, значит крафт обязан провалиться."""
    inventory = [item("сталь", 5), item("сталь", 2), item("дерево", 4)]
    with patch_dice(impl, return_value=0.0):
        result = impl.craft(inventory, "меч", 10)
    assert result is None


def test_dice_boundary_is_success(impl):
    """Шанс провала 0.2, кубик выпал ровно 0.2. Сравнение строгое, это успех."""
    inventory = [item("сталь", 5), item("сталь", 2), item("дерево", 4)]
    with patch_dice(impl, return_value=0.2):
        result = impl.craft(inventory, "меч", 10)
    assert result == {"name": "меч", "quality": 2}


def test_dice_called_once(impl):
    calls = []

    def fake():
        calls.append(1)
        return 1.0

    inventory = [item("сталь", 5), item("сталь", 2), item("дерево", 4)]
    with patch_dice(impl, side_effect=fake):
        impl.craft(inventory, "меч", 10)
    assert len(calls) == 1


def test_no_dice_on_refusal(impl):
    """Невозможный крафт: кубик вообще не бросают."""
    inventory = [item("палка"), item("смола")]

    def boom(*args, **kwargs):
        raise AssertionError("кубик не должен бросаться")

    with patch_dice(impl, side_effect=boom):
        with pytest.raises(ValueError):
            impl.craft(inventory, "факел", 0)
    assert inventory == [item("палка"), item("смола")]


# --- пункт 4: проверка уровня ---

def test_unknown_recipe(impl):
    inventory = [item("палка"), item("смола")]
    with pytest.raises(ValueError):
        impl.craft(inventory, "золотой ключ", 1)
    assert inventory == [item("палка"), item("смола")]


def test_level_too_low(impl):
    inventory = [item("звёздная пыль", 5), item("звёздная пыль", 5),
                 item("звёздная пыль", 5), item("дерево", 2)]
    with pytest.raises(ValueError):
        impl.craft(inventory, "посох архимага", 25)
    assert inventory == [item("звёздная пыль", 5), item("звёздная пыль", 5),
                         item("звёздная пыль", 5), item("дерево", 2)]


def test_level_must_be_int(impl):
    inventory = [item("палка"), item("смола")]
    for bad in (True, 1.0, "1", 0, -1, None):
        with pytest.raises(ValueError):
            impl.craft(list(inventory), "факел", bad)


def test_level_exactly_recipe_level(impl):
    """Уровень ровно как в рецепте, крафтить можно."""
    inventory = [item("сталь", 5), item("сталь", 2), item("дерево", 4)]
    with patch_dice(impl, return_value=1.0):
        result = impl.craft(inventory, "меч", 5)
    assert result == {"name": "меч", "quality": 2}


def test_level_check_survives_optimize(impl):
    """Проверка уровня должна работать и под python3 -O.

    Код Валеры использует assert, который -O выкидывает. Компилируем модуль
    с optimize=1 и проверяем, что отказ по уровню всё ещё ValueError.
    """
    source = open(impl.__file__, encoding="utf-8").read()
    code = compile(source, impl.__file__, "exec", optimize=1)
    namespace = {"__name__": "impl_optimized"}
    exec(code, namespace)
    craft = namespace["craft"]

    inventory = [item("звёздная пыль", 5), item("звёздная пыль", 5),
                 item("звёздная пыль", 5), item("дерево", 2)]
    with pytest.raises(ValueError):
        craft(inventory, "посох архимага", 25)

    with pytest.raises(ValueError):
        craft([item("палка"), item("смола")], "факел", True)


# --- остальные правила ---

def test_equipped_item_not_ingredient(impl):
    inventory = [item("палка", 2, equipped=True), item("смола", 3)]
    with pytest.raises(ValueError):
        impl.craft(inventory, "факел", 1)
    assert inventory == [item("палка", 2, equipped=True), item("смола", 3)]


def test_full_inventory(impl):
    """Инвентарь полон, а для меча шанс провала больше нуля.

    Проверяем, что кубик не бросают: отказ по вместимости должен случиться
    раньше. Если кубик кинется, side_effect поднимет AssertionError.
    """
    inventory = [item("сталь", 5), item("сталь", 2), item("дерево", 4)]
    inventory += [item("хлам", q) for q in range(1, 8)]
    assert len(inventory) == CAPACITY
    before = list(inventory)

    def boom(*args, **kwargs):
        raise AssertionError("кубик не должен бросаться")

    with patch_dice(impl, side_effect=boom):
        with pytest.raises(ValueError):
            impl.craft(inventory, "меч", 10)
    assert inventory == before
