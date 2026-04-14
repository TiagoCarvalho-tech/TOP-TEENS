from datetime import date, datetime
import re

from psycopg.errors import UniqueViolation

from database import get_connection


def gerar_matricula(connection):
    ano_atual = datetime.now().year
    cursor = connection.execute(
        """
        SELECT COALESCE(
            MAX(
                CASE
                    WHEN matricula ~ '^[0-9]{8}$' THEN CAST(RIGHT(matricula, 4) AS INTEGER)
                    ELSE 0
                END
            ),
            0
        ) AS ultimo
        FROM adolescentes
        WHERE matricula LIKE %s
        """,
        (f"{ano_atual}%",),
    )
    sequencia = cursor.fetchone()["ultimo"] + 1
    return f"{ano_atual}{sequencia:04d}"


def normalizar_nome(texto):
    texto = re.sub(r"\s+", " ", (texto or "").strip())
    return " ".join(parte.capitalize() for parte in texto.split())


def normalizar_contato(contato):
    numeros = re.sub(r"\D", "", contato or "")
    if not numeros:
        return ""
    if len(numeros) == 11:
        return f"({numeros[:2]}) {numeros[2:7]}-{numeros[7:]}"
    if len(numeros) == 10:
        return f"({numeros[:2]}) {numeros[2:6]}-{numeros[6:]}"
    return numeros


def listar_adolescentes(busca="", lider_ga="", sexo="", lider_id=None):
    filtros = []
    parametros = []

    if busca:
        filtros.append("(nome ILIKE %s OR matricula ILIKE %s)")
        termo = f"%{busca.strip()}%"
        parametros.extend([termo, termo])

    if lider_id is not None:
        filtros.append("lider_id = %s")
        parametros.append(int(lider_id))
    elif lider_ga:
        filtros.append("lider_ga = %s")
        parametros.append(lider_ga)

    if sexo:
        filtros.append("sexo = %s")
        parametros.append(sexo)

    where = ""
    if filtros:
        where = "WHERE " + " AND ".join(filtros)

    consulta = f"""
        SELECT *
        FROM adolescentes
        {where}
        ORDER BY nome
    """

    with get_connection() as connection:
        return connection.execute(consulta, parametros).fetchall()


def listar_lideres_ga():
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT DISTINCT lider_ga
            FROM adolescentes
            WHERE lider_ga <> ''
            ORDER BY lider_ga
            """
        ).fetchall()
    return [row["lider_ga"] for row in rows]


def obter_adolescente(adolescente_id):
    with get_connection() as connection:
        return connection.execute(
            "SELECT * FROM adolescentes WHERE id = %s",
            (adolescente_id,),
        ).fetchone()


def cadastrar_adolescente(dados):
    with get_connection() as connection:
        for _ in range(8):
            matricula = gerar_matricula(connection)
            try:
                adolescente = connection.execute(
                    """
                    INSERT INTO adolescentes (
                        lider_id, matricula, foto_path, nome, nascimento, contato, sexo, pai, mae, lider_ga
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id, matricula
                    """,
                    (
                        int(dados["lider_id"]) if str(dados.get("lider_id", "")).isdigit() else None,
                        matricula,
                        dados.get("foto_path", "").strip(),
                        normalizar_nome(dados["nome"]),
                        dados["nascimento"],
                        normalizar_contato(dados.get("contato", "")),
                        dados["sexo"],
                        normalizar_nome(dados.get("responsavel", "")),
                        "",
                        normalizar_nome(dados["lider_ga"]),
                    ),
                ).fetchone()
                return adolescente
            except UniqueViolation:
                connection.rollback()
                continue
    raise RuntimeError("Não foi possível gerar matrícula única para o adolescente.")


def atualizar_adolescente(adolescente_id, dados):
    with get_connection() as connection:
        connection.execute(
            """
            UPDATE adolescentes
            SET lider_id = %s, foto_path = %s, nome = %s, nascimento = %s, contato = %s, sexo = %s, pai = %s, mae = %s, lider_ga = %s
            WHERE id = %s
            """,
            (
                int(dados["lider_id"]) if str(dados.get("lider_id", "")).isdigit() else None,
                dados.get("foto_path", "").strip(),
                normalizar_nome(dados["nome"]),
                dados["nascimento"],
                normalizar_contato(dados.get("contato", "")),
                dados["sexo"],
                normalizar_nome(dados.get("responsavel", "")),
                "",
                normalizar_nome(dados["lider_ga"]),
                adolescente_id,
            ),
        )


def excluir_adolescente(adolescente_id):
    with get_connection() as connection:
        connection.execute("DELETE FROM adolescentes WHERE id = %s", (adolescente_id,))


def aniversariantes_proximos(dias=30):
    hoje = date.today()
    aniversariantes = []

    with get_connection() as connection:
        rows = connection.execute(
            "SELECT id, nome, matricula, nascimento, lider_ga FROM adolescentes ORDER BY nome"
        ).fetchall()

    for adolescente in rows:
        nascimento = datetime.strptime(adolescente["nascimento"], "%Y-%m-%d").date()
        try:
            proximo = nascimento.replace(year=hoje.year)
        except ValueError:
            # Ajusta anos não bissextos para aniversários em 29/02.
            proximo = nascimento.replace(year=hoje.year, day=28)
        if proximo < hoje:
            try:
                proximo = proximo.replace(year=hoje.year + 1)
            except ValueError:
                proximo = proximo.replace(year=hoje.year + 1, day=28)

        faltam = (proximo - hoje).days
        if faltam <= dias:
            aniversariantes.append(
                {
                    "id": adolescente["id"],
                    "nome": adolescente["nome"],
                    "matricula": adolescente["matricula"],
                    "lider_ga": adolescente["lider_ga"],
                    "data_aniversario": proximo,
                    "faltam": faltam,
                }
            )

    return sorted(aniversariantes, key=lambda item: item["faltam"])
