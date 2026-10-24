"""Мимик: делает из вашего craft.py мутантов и проверяет, заметят ли их ваши тесты.

    python3 mimic.py              # таблица в терминал
    python3 mimic.py > mimic.txt  # она же в файл, для сдачи

Мутант — craft.py с одной маленькой правкой. Если ваши тесты на мутанте
остались зелёными, мутант выжил: тесты не заметили, что код сломан.

Ваша часть — функция mutants(). Всё остальное уже написано.
"""
import ast
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))


def mutants(source):
    """Все мутанты исходника source. Каждый отличается от оригинала ровно одной правкой:

      1. одно сравнение сдвинуто на границе: < и <=, > и >=, == и != меняются друг на друга;
      2. один and становится or, или один or становится and;
      3. две соседние инструкции одного блока меняются местами;
      4. одна инструкция заменяется на pass.

    Блок — список инструкций в поле body или orelse любого узла, кроме самого
    модуля: верхний уровень файла (импорты, def) не трогаем.

    Возвращает список исходников — строк, которые напечатал ast.unparse.
    Подсказка: каждого мутанта делайте из свежего дерева. Порядок узлов в
    ast.walk для одного и того же исходника всегда один и тот же, поэтому
    нужный узел в свежем дереве можно найти по его номеру.
    """
    _SHIFT = {
        ast.Lt: ast.LtE,
        ast.LtE: ast.Lt,
        ast.Gt: ast.GtE,
        ast.GtE: ast.Gt,
        ast.Eq: ast.NotEq,
        ast.NotEq: ast.Eq,
    }

    original_nodes = list(ast.walk(ast.parse(source)))
    produced = []

    def emit(edit):
        tree = ast.parse(source)
        fresh = list(ast.walk(tree))
        edit(fresh)
        produced.append(ast.unparse(tree))

    for idx, node in enumerate(original_nodes):
        if isinstance(node, ast.Compare):
            for pos, op in enumerate(node.ops):
                new_cls = _SHIFT.get(type(op))
                if new_cls is not None:
                    emit(_shift_op(idx, pos, new_cls))

        if isinstance(node, ast.BoolOp) and isinstance(node.op, (ast.And, ast.Or)):
            emit(_flip_bool(idx))

        if isinstance(node, ast.Module):
            continue
        for field in ("body", "orelse"):
            block = getattr(node, field, None)
            if not isinstance(block, list):
                continue
            for k in range(len(block) - 1):
                emit(_swap(idx, field, k))
            for k in range(len(block)):
                if isinstance(block[k], ast.Pass):
                    continue
                emit(_to_pass(idx, field, k))

    seen = set()
    result = []
    for mutant in produced:
        if mutant not in seen:
            seen.add(mutant)
            result.append(mutant)
    return result


def _shift_op(idx, pos, new_cls):
    def edit(nodes):
        nodes[idx].ops[pos] = new_cls()
    return edit


def _flip_bool(idx):
    def edit(nodes):
        op = nodes[idx].op
        nodes[idx].op = ast.Or() if isinstance(op, ast.And) else ast.And()
    return edit


def _swap(idx, field, k):
    def edit(nodes):
        block = getattr(nodes[idx], field)
        block[k], block[k + 1] = block[k + 1], block[k]
    return edit


def _to_pass(idx, field, k):
    def edit(nodes):
        getattr(nodes[idx], field)[k] = ast.Pass()
    return edit


# ---------------------------------------------------------------- дальше уже написано


def run_suite(source):
    """Прогнать test_craft.py, подложив source вместо craft.py. True — тесты зелёные."""
    with tempfile.TemporaryDirectory() as tmp:
        for name in ("recipes.py", "conftest.py", "test_craft.py"):
            shutil.copy(os.path.join(HERE, name), tmp)
        with open(os.path.join(tmp, "craft.py"), "w", encoding="utf-8") as f:
            f.write(source)
        done = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", "-x", "-p", "no:cacheprovider"],
            cwd=tmp, capture_output=True, text=True, timeout=300,
        )
        return done.returncode == 0


def what_changed(original, mutant):
    """Короткое описание правки для таблицы."""
    old, new = original.splitlines(), mutant.splitlines()
    i = next((k for k in range(min(len(old), len(new))) if old[k] != new[k]), min(len(old), len(new)))
    if i >= min(len(old), len(new)):
        return "правка в самом конце файла"
    if sorted(old) == sorted(new):
        return f"строка {i + 1}: переставлены «{old[i].strip()}» и «{new[i].strip()}»"
    if new[i].strip() == "pass":
        return f"строка {i + 1}: «{old[i].strip()}» заменено на pass"
    return f"строка {i + 1}: {old[i].strip()}  ->  {new[i].strip()}"


def without_docstrings(source):
    """Исходник без докстрингов: мутант, который двигает строку-описание, ничего не ломает."""
    tree = ast.parse(source)
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if (isinstance(body, list) and body and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant) and isinstance(body[0].value.value, str)):
            del body[0]
            if not body:
                body.append(ast.Pass())
    return ast.unparse(tree)


def main():
    with open(os.path.join(HERE, "craft.py"), encoding="utf-8") as f:
        original = without_docstrings(f.read())
    if not run_suite(original):
        sys.exit("Тесты красные на вашем же craft.py: сначала почините их.")
    print("Строки считаются в craft.py, пересобранном через ast.unparse без докстрингов.\n")
    alive = 0
    for number, mutant in enumerate(mutants(original), 1):
        try:
            compile(mutant, "craft.py", "exec")
        except SyntaxError:
            status = "не компилируется"
        else:
            survived = run_suite(mutant)
            alive += survived
            status = "ВЫЖИЛ" if survived else "убит"
        print(f"{number:3}  {status:17} {what_changed(original, mutant)}")
    print(f"\nвыжило мутантов: {alive}")


if __name__ == "__main__":
    main()
