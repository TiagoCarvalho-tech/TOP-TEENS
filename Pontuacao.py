from database import get_connection


FASE1_SEMANAS = [
    "2026-03-15",
    "2026-03-22",
    "2026-03-29",
    "2026-04-12",
]

PONTOS_FIXOS = {
    "P": 10,
    "MV": 20,
    "AB": 10,
    "V": 1,
    "APPS": 40,
}

SINONIMOS_ATIVIDADE = {
    "P": {"presença", "presenca", "presença culto"},
    "MV": {"meditação e versículo", "meditacao e versiculo", "meditação e versiculo", "meditação"},
    "AB": {"anotação e bíblia", "anotacao e biblia", "bíblia e anotação", "biblia e anotacao"},
    "V": {"visitante"},
    "APPS": {"apps"},
}


def _normalizar_nome(nome):
    return (nome or "").strip().lower()


def _carregar_mapa_ids_atividades():
    mapa = {"P": set(), "MV": set(), "AB": set(), "V": set(), "APPS": set()}
    with get_connection() as connection:
        atividades = connection.execute(
            """
            SELECT id, nome
            FROM atividades
            WHERE ativo = 1
            """
        ).fetchall()

    for atividade in atividades:
        nome = _normalizar_nome(atividade["nome"])
        for chave, sinonimos in SINONIMOS_ATIVIDADE.items():
            if nome in sinonimos:
                mapa[chave].add(atividade["id"])
                break
    return mapa


def _cumprimentos_ativos():
    ids = _carregar_mapa_ids_atividades()
    ids_todos = list(ids["P"] | ids["MV"] | ids["AB"] | ids["V"] | ids["APPS"])
    if not ids_todos:
        return [], ids

    placeholders = ", ".join(["%s"] * len(ids_todos))
    with get_connection() as connection:
        rows = connection.execute(
            f"""
            WITH ultimos AS (
                SELECT
                    ct.*,
                    ROW_NUMBER() OVER (
                        PARTITION BY ct.adolescente_id, ct.atividade_id, ct.data_cumprimento
                        ORDER BY ct.id DESC
                    ) AS pos
                FROM cumprimentos_tarefas ct
                WHERE ct.atividade_id IN ({placeholders})
            )
            SELECT *
            FROM ultimos
            WHERE pos = 1 AND cumpriu = 1
            """,
            ids_todos,
        ).fetchall()
    return rows, ids


def _mapa_adolescentes():
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT id, nome, sexo, lider_ga, matricula, foto_path
            FROM adolescentes
            ORDER BY nome
            """
        ).fetchall()
    return {item["id"]: item for item in rows}


def mapa_pontuacao_por_adolescente():
    adolescentes = _mapa_adolescentes()
    cumprimentos, ids = _cumprimentos_ativos()

    resultado = {}
    for adolescente_id, adolescente in adolescentes.items():
        resultado[adolescente_id] = {
            "id": adolescente_id,
            "nome": adolescente["nome"],
            "sexo": adolescente["sexo"],
            "lider_ga": adolescente["lider_ga"],
            "matricula": adolescente["matricula"],
            "foto_path": adolescente["foto_path"],
            "semanas": {data: 0 for data in FASE1_SEMANAS},
            "apps_marcado": False,
            "pontos_tarefas": 0,
            "pontos_apps_fase": 0,
            "total_pontos": 0,
            "cupons": 0,
        }

    for row in cumprimentos:
        adolescente_id = row["adolescente_id"]
        if adolescente_id not in resultado:
            continue

        atividade_id = row["atividade_id"]
        data = row["data_cumprimento"]

        if atividade_id in ids["APPS"]:
            if data in FASE1_SEMANAS:
                resultado[adolescente_id]["apps_marcado"] = True
            continue

        if data not in FASE1_SEMANAS:
            continue

        if atividade_id in ids["P"]:
            resultado[adolescente_id]["semanas"][data] += PONTOS_FIXOS["P"]
        elif atividade_id in ids["MV"]:
            resultado[adolescente_id]["semanas"][data] += PONTOS_FIXOS["MV"]
        elif atividade_id in ids["AB"]:
            resultado[adolescente_id]["semanas"][data] += PONTOS_FIXOS["AB"]
        elif atividade_id in ids["V"]:
            resultado[adolescente_id]["semanas"][data] += PONTOS_FIXOS["V"]

    for adolescente_id, item in resultado.items():
        pontos_tarefas = sum(item["semanas"].values())
        pontos_apps = PONTOS_FIXOS["APPS"] if item["apps_marcado"] else 0
        total = pontos_tarefas + pontos_apps

        item["pontos_tarefas"] = pontos_tarefas
        item["pontos_apps_fase"] = pontos_apps
        item["total_pontos"] = total
        item["cupons"] = total // 80

    return resultado


def resumo_adolescente(adolescente_id):
    mapa = mapa_pontuacao_por_adolescente()
    return mapa.get(adolescente_id)


def ranking_geral():
    ranking = list(mapa_pontuacao_por_adolescente().values())
    ranking.sort(
        key=lambda item: (-item["total_pontos"], item["nome"].lower()),
    )
    return ranking


def ranking_por_sexo():
    base = ranking_geral()
    return {
        "M": [item for item in base if item["sexo"] == "M"],
        "F": [item for item in base if item["sexo"] == "F"],
    }


def resumo_dashboard():
    ranking = ranking_geral()
    return {
        "total_adolescentes": len(ranking),
        "total_pontos": sum(item["total_pontos"] for item in ranking),
        "lideres_ga": sorted({item["lider_ga"] for item in ranking if item["lider_ga"]}),
        "top_5": ranking[:5],
    }
