from database import get_connection


def listar_atividades(somente_ativas=False, incluir_apps=True):
    filtros = []
    if somente_ativas:
        filtros.append("ativo = 1")
    if not incluir_apps:
        filtros.append("lower(nome) <> lower('Apps')")

    filtro = ""
    if filtros:
        filtro = "WHERE " + " AND ".join(filtros)

    with get_connection() as connection:
        return connection.execute(
            f"""
            SELECT *
            FROM atividades
            {filtro}
            ORDER BY ativo DESC, nome
            """
        ).fetchall()


def obter_atividade(atividade_id):
    with get_connection() as connection:
        return connection.execute(
            "SELECT * FROM atividades WHERE id = %s",
            (atividade_id,),
        ).fetchone()


def existe_cumprimento_no_dia(adolescente_id, atividade_id, data_cumprimento, excluir_id=None):
    consulta = """
        SELECT id
        FROM cumprimentos_tarefas
        WHERE adolescente_id = %s
          AND atividade_id = %s
          AND data_cumprimento = %s
    """
    parametros = [int(adolescente_id), int(atividade_id), data_cumprimento]

    if excluir_id is not None:
        consulta += " AND id <> %s"
        parametros.append(int(excluir_id))

    consulta += " LIMIT 1"

    with get_connection() as connection:
        row = connection.execute(consulta, parametros).fetchone()
    return row is not None


def mapa_datas_lancadas_por_atividade(atividade_id):
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT adolescente_id, data_cumprimento
            FROM cumprimentos_tarefas
            WHERE atividade_id = %s
            ORDER BY data_cumprimento
            """,
            (int(atividade_id),),
        ).fetchall()

    resultado = {}
    for row in rows:
        chave = str(row["adolescente_id"])
        resultado.setdefault(chave, [])
        if row["data_cumprimento"] not in resultado[chave]:
            resultado[chave].append(row["data_cumprimento"])
    return resultado


def obter_id_atividade_por_nome(nome):
    with get_connection() as connection:
        atividade = connection.execute(
            """
            SELECT id
            FROM atividades
            WHERE lower(trim(nome)) = lower(%s)
            LIMIT 1
            """,
            (nome,),
        ).fetchone()
    return atividade["id"] if atividade else None


def cadastrar_atividade(dados):
    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO atividades (nome, pontos, descricao, ativo)
            VALUES (%s, %s, %s, %s)
            """,
            (
                dados["nome"].strip(),
                int(dados["pontos"]),
                dados.get("descricao", "").strip(),
                int(dados.get("ativo", 1)),
            ),
        )


def atualizar_atividade(atividade_id, dados):
    with get_connection() as connection:
        connection.execute(
            """
            UPDATE atividades
            SET nome = %s, pontos = %s, descricao = %s, ativo = %s
            WHERE id = %s
            """,
            (
                dados["nome"].strip(),
                int(dados["pontos"]),
                dados.get("descricao", "").strip(),
                int(dados.get("ativo", 1)),
                atividade_id,
            ),
        )


def excluir_atividade(atividade_id):
    with get_connection() as connection:
        connection.execute("DELETE FROM atividades WHERE id = %s", (atividade_id,))


def listar_cumprimentos(adolescente_id=None):
    parametros = []
    filtro = ""
    if adolescente_id:
        filtro = "WHERE ct.adolescente_id = %s"
        parametros.append(adolescente_id)

    with get_connection() as connection:
        return connection.execute(
            f"""
            SELECT
                ct.*,
                a.nome AS atividade_nome,
                a.pontos AS atividade_pontos,
                ad.nome AS adolescente_nome,
                ad.matricula AS adolescente_matricula
            FROM cumprimentos_tarefas ct
            JOIN atividades a ON a.id = ct.atividade_id
            JOIN adolescentes ad ON ad.id = ct.adolescente_id
            {filtro}
            ORDER BY ct.data_cumprimento DESC, ct.id DESC
            """,
            parametros,
        ).fetchall()


def obter_cumprimento(cumprimento_id):
    with get_connection() as connection:
        return connection.execute(
            """
            SELECT *
            FROM cumprimentos_tarefas
            WHERE id = %s
            """,
            (cumprimento_id,),
        ).fetchone()


def registrar_cumprimento(dados):
    presenca_id = dados.get("presenca_id")
    atividade_id = int(dados["atividade_id"])
    cumpriu = int(dados["cumpriu"])
    falta_justificada = 0
    if presenca_id is not None and atividade_id == int(presenca_id) and cumpriu == 0:
        falta_justificada = int(str(dados.get("falta_justificada", "0")).strip() == "1")

    with get_connection() as connection:
        return connection.execute(
            """
            INSERT INTO cumprimentos_tarefas (
                adolescente_id, atividade_id, data_cumprimento, cumpriu, observacoes, falta_justificada
            ) VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id, atividade_id
            """,
            (
                int(dados["adolescente_id"]),
                atividade_id,
                dados["data_cumprimento"],
                cumpriu,
                dados.get("observacoes", "").strip(),
                falta_justificada,
            ),
        ).fetchone()


def registrar_cumprimentos_em_lote(dados, atividade_ids, presenca_id=None):
    cumpriu = int(dados["cumpriu"])
    justificou = int(str(dados.get("falta_justificada", "0")).strip() == "1")

    with get_connection() as connection:
        registros = []
        for atividade_id in atividade_ids:
            atividade_id_int = int(atividade_id)
            falta_justificada = 0
            if presenca_id is not None and atividade_id_int == int(presenca_id) and cumpriu == 0:
                falta_justificada = justificou

            registro = connection.execute(
                """
                INSERT INTO cumprimentos_tarefas (
                    adolescente_id, atividade_id, data_cumprimento, cumpriu, observacoes, falta_justificada
                ) VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING id, atividade_id
                """,
                (
                    int(dados["adolescente_id"]),
                    atividade_id_int,
                    dados["data_cumprimento"],
                    cumpriu,
                    dados.get("observacoes", "").strip(),
                    falta_justificada,
                ),
            ).fetchone()
            registros.append(registro)
    return registros


def atualizar_cumprimento(cumprimento_id, dados, presenca_id=None):
    atividade_id = int(dados["atividade_id"])
    cumpriu = int(dados["cumpriu"])
    falta_justificada = 0
    if presenca_id is not None and atividade_id == int(presenca_id) and cumpriu == 0:
        falta_justificada = int(str(dados.get("falta_justificada", "0")).strip() == "1")

    with get_connection() as connection:
        connection.execute(
            """
            UPDATE cumprimentos_tarefas
            SET adolescente_id = %s, atividade_id = %s, data_cumprimento = %s, cumpriu = %s, observacoes = %s, falta_justificada = %s
            WHERE id = %s
            """,
            (
                int(dados["adolescente_id"]),
                atividade_id,
                dados["data_cumprimento"],
                cumpriu,
                dados.get("observacoes", "").strip(),
                falta_justificada,
                cumprimento_id,
            ),
        )


def excluir_cumprimento(cumprimento_id):
    with get_connection() as connection:
        connection.execute("DELETE FROM cumprimentos_tarefas WHERE id = %s", (cumprimento_id,))
