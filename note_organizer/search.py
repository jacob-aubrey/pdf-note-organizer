"""Small Boolean query parser. User text is never evaluated as Python or SQL."""


class SearchSyntaxError(ValueError):
    pass


def normalize(text):
    return " ".join(str(text).casefold().split())


def tokenize(query):
    tokens, i = [], 0
    while i < len(query):
        if query[i].isspace():
            i += 1
            continue
        char = query[i]
        if char in "()":
            tokens.append((char, char))
            i += 1
        elif char == '"':
            i += 1
            phrase = []
            while i < len(query) and query[i] != '"':
                if query[i] == "\\" and i+1 < len(query) and query[i+1] in {'"', "\\"}:
                    i += 1
                phrase.append(query[i])
                i += 1
            if i == len(query):
                raise SearchSyntaxError('Close the quoted phrase with a double quote (").')
            i += 1
            phrase = normalize("".join(phrase))
            if not phrase:
                raise SearchSyntaxError("Put some text inside the quotes.")
            tokens.append(("TERM", phrase))
        else:
            start = i
            while i < len(query) and not query[i].isspace() and query[i] not in '()"':
                i += 1
            word = query[start:i]
            tokens.append((word, word) if word in {"AND", "OR", "NOT"} else ("TERM", normalize(word)))
        if len(tokens) > 256:
            raise SearchSyntaxError("This search is too long. Use fewer terms.")
    return tokens


def compile_search(query, mode="All words"):
    if len(query) > 4096:
        raise SearchSyntaxError("This search is too long. Use fewer terms.")
    if not query.strip():
        return lambda values: True
    if mode == "Exact phrase":
        phrase = normalize(query)
        return lambda values: any(phrase in value for value in values)
    tokens = tokenize(query)
    position = 0

    def peek():
        return tokens[position][0] if position < len(tokens) else "END"

    def unary(depth=0):
        nonlocal position
        if depth > 32:
            raise SearchSyntaxError("Too many nested parentheses or NOT operators.")
        kind = peek()
        if kind == "NOT":
            position += 1
            return ("NOT", unary(depth+1))
        if kind == "(":
            position += 1
            result = disjunction(depth+1)
            if peek() != ")":
                raise SearchSyntaxError("Close the parenthesis with ).")
            position += 1
            return result
        if kind != "TERM":
            raise SearchSyntaxError("Expected a word, quoted phrase, or group after the operator.")
        result = tokens[position]
        position += 1
        return result

    def conjunction(depth):
        nonlocal position
        left = unary(depth)
        while peek() in {"AND", "TERM", "(", "NOT"}:
            if peek() == "AND":
                position += 1
            left = ("AND", left, unary(depth))
        return left

    def disjunction(depth):
        nonlocal position
        left = conjunction(depth)
        while peek() == "OR":
            position += 1
            left = ("OR", left, conjunction(depth))
        return left

    expression = disjunction(0)
    if position != len(tokens):
        raise SearchSyntaxError("Unexpected closing parenthesis. Check the groups in your search.")

    def evaluate(node, values):
        op = node[0]
        if op == "TERM":
            return any(node[1] in value for value in values)
        if op == "NOT":
            return not evaluate(node[1], values)
        if op == "AND":
            return evaluate(node[1], values) and evaluate(node[2], values)
        return evaluate(node[1], values) or evaluate(node[2], values)

    return lambda values: evaluate(expression, values)
