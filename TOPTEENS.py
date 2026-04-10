from datetime import date, datetime, timedelta
from functools import wraps
from io import BytesIO
from os import environ
from pathlib import Path
import re
import secrets

from flask import Flask, abort, flash, make_response, redirect, render_template, request, session, url_for
from fpdf import FPDF
from PIL import Image, ImageOps, UnidentifiedImageError
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

import Adolescente
import Atividade
import Pontuacao
from database import get_connection, init_db


app = Flask(__name__)
BASE_DIR = Path(__file__).resolve().parent
SECRET_FILE = BASE_DIR / ".secret_key"


def carregar_secret_key():
    chave_ambiente = environ.get("TOPTEENS_SECRET_KEY")
    if chave_ambiente:
        return chave_ambiente

    if SECRET_FILE.exists():
        return SECRET_FILE.read_text(encoding="utf-8").strip()

    nova_chave = secrets.token_urlsafe(48)
    SECRET_FILE.write_text(nova_chave, encoding="utf-8")
    return nova_chave


app.config["SECRET_KEY"] = carregar_secret_key()
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = environ.get("TOPTEENS_HTTPS_ONLY", "0") == "1"
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(hours=8)


def inteiro_positivo_ambiente(chave, padrao):
    valor = (environ.get(chave, "") or "").strip()
    try:
        numero = int(valor)
    except (TypeError, ValueError):
        numero = padrao
    return max(1, numero)


MAX_UPLOAD_MB = inteiro_positivo_ambiente("TOPTEENS_MAX_UPLOAD_MB", 10)
MAX_UPLOAD_BYTES = MAX_UPLOAD_MB * 1024 * 1024
MAX_IMAGE_DIMENSION = 1024
app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_BYTES
app.config["MAX_FORM_MEMORY_SIZE"] = MAX_UPLOAD_BYTES + (256 * 1024)
FASE1_SEMANAS = [
    ("Semana 1", "2026-03-15"),
    ("Semana 2", "2026-03-22"),
    ("Semana 3", "2026-03-29"),
    ("Semana 4", "2026-04-12"),
]
DATAS_FASE1 = {data for _, data in FASE1_SEMANAS}
DATAS_FASE1_APPS = set(DATAS_FASE1)
UPLOADS_DIR = BASE_DIR / "static" / "uploads"
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
EXTENSOES_FOTO_PERMITIDAS = {"jpg", "jpeg", "png"}

ATIVIDADES_FASE = {
    "P": {"nome": "Presença", "pontos": 10, "aliases": {"presença", "presenca", "presença culto"}},
    "MV": {"nome": "Meditação e Versículo", "pontos": 20, "aliases": {"meditação e versículo", "meditacao e versiculo", "meditação"}},
    "AB": {"nome": "Anotação e Bíblia", "pontos": 10, "aliases": {"anotação e bíblia", "anotacao e biblia", "bíblia e anotação", "biblia e anotacao"}},
    "V": {"nome": "Visitante", "pontos": 1, "aliases": {"visitante"}},
    "APPS": {"nome": "APPS", "pontos": 40, "aliases": {"apps"}},
}
SENHA_LIDER_MASTER = "2026SA@"


def login_obrigatorio(view):
    @wraps(view)
    def wrapped_view(**kwargs):
        if "usuario_id" not in session:
            flash("Faça login para continuar.", "warning")
            return redirect(url_for("login"))
        return view(**kwargs)

    return wrapped_view


def master_obrigatorio(view):
    @wraps(view)
    def wrapped_view(**kwargs):
        if "usuario_id" not in session:
            flash("Faça login para continuar.", "warning")
            return redirect(url_for("login"))
        if session.get("usuario_role") != "MASTER":
            abort(403)
        return view(**kwargs)

    return wrapped_view


def gerar_csrf_token():
    token = session.get("_csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        session["_csrf_token"] = token
    return token


def csrf_valido():
    token_sessao = session.get("_csrf_token")
    token_formulario = request.form.get("_csrf_token", "")
    return bool(token_sessao) and secrets.compare_digest(token_sessao, token_formulario)


def usuario_master():
    return session.get("usuario_role") == "MASTER"


def normalizar_texto(texto):
    return re.sub(r"\s+", " ", (texto or "").strip())


def idade_por_data_iso(data_iso):
    if not data_iso:
        return None
    try:
        nascimento = datetime.strptime(data_iso, "%Y-%m-%d").date()
    except ValueError:
        return None

    hoje = date.today()
    idade = hoje.year - nascimento.year
    if (hoje.month, hoje.day) < (nascimento.month, nascimento.day):
        idade -= 1
    return idade


def aniversario_curto(data_iso):
    if not data_iso:
        return "-"
    try:
        nascimento = datetime.strptime(data_iso, "%Y-%m-%d").date()
    except ValueError:
        return "-"
    return nascimento.strftime("%d/%m")


def somente_letras_espacos(texto):
    return bool(re.fullmatch(r"[A-Za-zÀ-ÿ' -]+", texto))


def nome_slug(texto):
    base = re.sub(r"[^a-z0-9]+", "-", normalizar_texto(texto).lower())
    return base.strip("-")


def obter_lider_ga_usuario():
    return normalizar_texto(session.get("usuario_lider_ga", ""))


def lider_ga_configurado():
    return bool(obter_lider_ga_usuario())


def extensao_foto_permitida(filename):
    if "." not in filename:
        return False
    extensao = filename.rsplit(".", 1)[1].lower()
    return extensao in EXTENSOES_FOTO_PERMITIDAS


def mensagem_erro_upload_foto(codigo):
    mensagens = {
        "FORMATO_EXTENSAO": "Foto inválida. Envie apenas JPG, JPEG ou PNG.",
        "FORMATO_CONTEUDO": "A foto parece inválida ou corrompida. Escolha outra imagem JPG/PNG.",
        "PROCESSAMENTO": "Não foi possível processar a foto enviada. Tente outra imagem.",
        "SALVAR": "Não foi possível salvar a foto agora. Tente novamente em instantes.",
    }
    return mensagens.get(codigo, "Não foi possível processar a foto. Escolha outra imagem.")


def salvar_foto_adolescente(arquivo, nome_base):
    if not arquivo or not arquivo.filename:
        return "", None
    if not extensao_foto_permitida(arquivo.filename):
        return None, "FORMATO_EXTENSAO"

    extensao_origem = arquivo.filename.rsplit(".", 1)[1].lower()
    try:
        arquivo.stream.seek(0)
        with Image.open(arquivo.stream) as imagem:
            formato = (imagem.format or "").upper()
            if formato not in {"JPEG", "JPG", "PNG"}:
                return None, "FORMATO_CONTEUDO"

            imagem = ImageOps.exif_transpose(imagem)
            imagem.thumbnail((MAX_IMAGE_DIMENSION, MAX_IMAGE_DIMENSION), Image.Resampling.LANCZOS)

            conteudo = BytesIO()
            extensao_final = "png" if extensao_origem == "png" else "jpg"
            if extensao_final == "png":
                if imagem.mode not in {"RGB", "RGBA", "L", "P"}:
                    imagem = imagem.convert("RGBA")
                imagem.save(conteudo, format="PNG", optimize=True, compress_level=6)
            else:
                if imagem.mode != "RGB":
                    imagem = imagem.convert("RGB")
                imagem.save(conteudo, format="JPEG", quality=82, optimize=True, progressive=True)
    except (UnidentifiedImageError, OSError, ValueError):
        return None, "PROCESSAMENTO"

    nome_arquivo = secure_filename(f"{nome_slug(nome_base)}-{secrets.token_hex(8)}.{extensao_final}")
    destino = UPLOADS_DIR / nome_arquivo
    try:
        destino.write_bytes(conteudo.getvalue())
    except OSError:
        return None, "SALVAR"
    return f"uploads/{nome_arquivo}", None


@app.errorhandler(413)
def tratar_upload_grande(_erro):
    flash(
        f"Arquivo muito grande. Envie uma imagem de até {MAX_UPLOAD_MB}MB em JPG ou PNG.",
        "danger",
    )
    if request.method == "POST":
        return redirect(request.url), 303
    return redirect(url_for("listar_adolescentes")), 303


def mapear_atividades_fixas_ids():
    atividades = Atividade.listar_atividades(somente_ativas=True)
    ids = {}
    for atividade in atividades:
        nome = normalizar_texto(atividade["nome"]).lower()
        for codigo, dados in ATIVIDADES_FASE.items():
            if nome in dados["aliases"]:
                ids[codigo] = atividade["id"]
                break
    return ids


def data_permitida_fase1_apps(valor_data):
    if not valor_data:
        return False
    return valor_data in DATAS_FASE1


def criar_usuario_padrao():
    with get_connection() as connection:
        usuario = connection.execute(
            "SELECT id, aprovado FROM usuarios WHERE username = %s",
            ("tio",),
        ).fetchone()
        if usuario is None:
            connection.execute(
                """
                INSERT INTO usuarios (nome, username, senha_hash, role, aprovado, lider_ga)
                VALUES (%s, %s, %s, 'MASTER', 1, %s)
                """,
                ("Tio Responsável", "tio", generate_password_hash("topteens123"), "Administração"),
            )
        else:
            connection.execute(
                """
                UPDATE usuarios
                SET aprovado = 1
                WHERE username = 'tio'
                """
            )


def popular_atividades_iniciais():
    atividades_padrao = [
        ("Presença", 10, "Presença da semana"),
        ("Meditação e Versículo", 20, "Meditação + versículo"),
        ("Anotação e Bíblia", 10, "Leitura com anotação"),
        ("Visitante", 1, "Levar visitante"),
        ("APPS", 40, "Atividade especial da fase"),
    ]
    aliases = {
        "Presença culto": "Presença",
        "Meditação e versículo": "Meditação e Versículo",
        "Bíblia e anotação": "Anotação e Bíblia",
        "Apps": "APPS",
    }
    nomes_oficiais = {nome.lower().strip() for nome, _, _ in atividades_padrao}

    with get_connection() as connection:
        # Migração simples de nomes antigos para os novos, sem mexer nos pontos já ajustados manualmente.
        for nome_antigo, nome_novo in aliases.items():
            antigo = connection.execute(
                "SELECT id FROM atividades WHERE lower(nome) = lower(%s)",
                (nome_antigo,),
            ).fetchone()
            novo = connection.execute(
                "SELECT id FROM atividades WHERE lower(nome) = lower(%s)",
                (nome_novo,),
            ).fetchone()
            if antigo and not novo:
                connection.execute(
                    "UPDATE atividades SET nome = %s WHERE id = %s",
                    (nome_novo, antigo["id"]),
                )

        # Só cria atividades que não existem. Não sobrescreve alterações feitas pelo usuário.
        for nome, pontos, descricao in atividades_padrao:
            atividade = connection.execute(
                "SELECT id FROM atividades WHERE lower(trim(nome)) = lower(%s)",
                (nome,),
            ).fetchone()
            if atividade is None:
                connection.execute(
                    """
                    INSERT INTO atividades (nome, pontos, descricao, ativo)
                    VALUES (%s, %s, %s, 1)
                    """,
                    (nome, pontos, descricao),
                )
            else:
                connection.execute(
                    """
                    UPDATE atividades
                    SET pontos = %s, ativo = 1
                    WHERE id = %s
                    """,
                    (pontos, atividade["id"]),
                )

        # Mantém somente as atividades oficiais ativas.
        connection.execute(
            """
            UPDATE atividades
            SET ativo = CASE WHEN lower(trim(nome)) = ANY(%s) THEN 1 ELSE 0 END
            """,
            (list(nomes_oficiais),),
        )


def validar_password_forte(senha):
    if len(senha) < 12:
        return "A senha deve ter pelo menos 12 caracteres."
    if not re.search(r"[A-Z]", senha):
        return "A senha deve ter ao menos uma letra maiúscula."
    if not re.search(r"[a-z]", senha):
        return "A senha deve ter ao menos uma letra minúscula."
    if not re.search(r"\d", senha):
        return "A senha deve ter ao menos um número."
    if not re.search(r"[^A-Za-z0-9]", senha):
        return "A senha deve ter ao menos um caractere especial."
    return None


def validar_nome_pessoa(valor, label, obrigatorio=True):
    valor = normalizar_texto(valor)
    if not valor:
        if obrigatorio:
            return f"O campo {label} é obrigatório."
        return None
    if len(valor) < 3 or len(valor) > 80:
        return f"O campo {label} deve ter entre 3 e 80 caracteres."
    if not somente_letras_espacos(valor):
        return f"O campo {label} aceita apenas letras e espaços."
    return None


def validar_lider_ga(valor):
    valor = normalizar_texto(valor)
    if not valor:
        return "O campo Líder de GA é obrigatório."
    if len(valor) < 3 or len(valor) > 80:
        return "O campo Líder de GA deve ter entre 3 e 80 caracteres."
    if not somente_letras_espacos(valor):
        return "O campo Líder de GA aceita apenas letras e espaços."
    return None


def validar_contato(valor):
    valor = normalizar_texto(valor)
    if not valor:
        return None
    digitos = re.sub(r"\D", "", valor)
    if len(digitos) not in {10, 11}:
        return "Informe um contato válido com DDD."
    return None


def validar_nascimento(valor):
    if not valor:
        return "O campo Data de nascimento é obrigatório."
    try:
        nascimento = datetime.strptime(valor, "%Y-%m-%d").date()
    except ValueError:
        return "Informe uma data de nascimento válida."

    hoje = date.today()
    if nascimento > hoje:
        return "A data de nascimento não pode estar no futuro."
    if nascimento.year < 1950:
        return "A data de nascimento deve ser a partir de 1950."
    return None


def validar_campos_adolescente(formulario):
    for erro in [
        validar_nome_pessoa(formulario.get("nome"), "Nome"),
        validar_nascimento(formulario.get("nascimento")),
        "O campo Contato do responsável é obrigatório." if not normalizar_texto(formulario.get("contato")) else validar_contato(formulario.get("contato")),
        validar_nome_pessoa(formulario.get("responsavel"), "Nome do Responsável"),
    ]:
        if erro:
            return erro

    if formulario.get("sexo") not in {"M", "F"}:
        return "Selecione um gênero válido."
    return None


def validar_campos_atividade(formulario):
    nome = normalizar_texto(formulario.get("nome", ""))
    if not nome:
        return "O nome da atividade é obrigatório."
    if len(nome) < 2 or len(nome) > 80:
        return "O nome da atividade deve ter entre 2 e 80 caracteres."
    if not formulario.get("pontos", "").strip():
        return "Os pontos da atividade são obrigatórios."
    try:
        pontos = int(formulario["pontos"])
    except ValueError:
        return "Os pontos devem ser um número inteiro."
    if pontos < 0 or pontos > 1000:
        return "Os pontos da atividade devem ficar entre 0 e 1000."
    return None


def validar_campos_cumprimento(formulario):
    obrigatorios = ["adolescente_id", "atividade_id", "data_cumprimento", "cumpriu"]
    if any(not formulario.get(campo, "").strip() for campo in obrigatorios):
        return "Preencha adolescente, atividade, data e status do cumprimento."
    if formulario.get("cumpriu") not in {"0", "1"}:
        return "Selecione um status válido para o cumprimento."
    return None


def validar_campos_cumprimento_lote(formulario):
    if not formulario.get("adolescente_id", "").strip():
        return "Selecione o adolescente."
    atividade_ids = [item for item in request.form.getlist("atividade_ids") if item.strip()]
    if not atividade_ids:
        return "Selecione pelo menos uma atividade para lançar."
    if any(not atividade_id.isdigit() for atividade_id in atividade_ids):
        return "Há uma atividade inválida na seleção."

    apps_id = Atividade.obter_id_atividade_por_nome("APPS")
    atividade_ids_int = {int(item) for item in atividade_ids}
    apps_selecionado = bool(apps_id and apps_id in atividade_ids_int)
    if apps_selecionado:
        if not formulario.get("apps_data_cumprimento", "").strip():
            return "Selecione a data do APPS."
        if formulario.get("apps_cumpriu") not in {"0", "1"}:
            return "Selecione se o adolescente estava presente no APPS."
        if not data_permitida_fase1_apps(formulario.get("apps_data_cumprimento")):
            return "A data do APPS deve ser uma das datas da fase 1."

    tem_outras_atividades = any(
        atividade_id != apps_id for atividade_id in atividade_ids_int
    )
    if tem_outras_atividades and not formulario.get("data_cumprimento", "").strip():
        return "Informe a data para as demais atividades selecionadas."

    atividade_nao_cumpriu_id = Atividade.obter_id_atividade_por_nome("Não cumpriu nenhuma atividade")
    if atividade_nao_cumpriu_id and str(atividade_nao_cumpriu_id) in atividade_ids and len(atividade_ids) > 1:
        return "Se marcar 'Não cumpriu nenhuma atividade', selecione somente essa atividade."
    return None


def validar_troca_senha(formulario):
    senha_atual = formulario.get("senha_atual", "")
    nova_senha = formulario.get("nova_senha", "")
    confirmar_senha = formulario.get("confirmar_senha", "")

    if not senha_atual or not nova_senha or not confirmar_senha:
        return "Preencha a senha atual e a nova senha completa."
    if nova_senha != confirmar_senha:
        return "A confirmação da nova senha não confere."
    return validar_password_forte(nova_senha)


def validar_atualizacao_perfil(formulario):
    for erro in [
        validar_nome_pessoa(formulario.get("nome"), "Nome"),
        validar_lider_ga(formulario.get("lider_ga")),
    ]:
        if erro:
            return erro
    return None


def validar_cadastro_usuario(formulario):
    nome = normalizar_texto(formulario.get("nome"))
    aniversario = formulario.get("aniversario")
    lider_ga = normalizar_texto(formulario.get("lider_ga"))
    senha = formulario.get("senha", "")

    erro_aniversario = None
    if not aniversario:
        erro_aniversario = "O campo Aniversário é obrigatório."
    else:
        erro_aniversario = validar_nascimento(aniversario)
        if erro_aniversario:
            erro_aniversario = erro_aniversario.replace("Data de nascimento", "Aniversário")

    for erro in [
        validar_nome_pessoa(nome, "Nome"),
        validar_lider_ga(lider_ga),
        erro_aniversario,
    ]:
        if erro:
            return erro

    erro_senha = validar_password_forte(senha)
    if erro_senha:
        return erro_senha
    return None


def usuario_pode_acessar_adolescente(adolescente):
    if adolescente is None:
        return False
    if usuario_master():
        return True
    usuario_id = session.get("usuario_id")
    if not usuario_id:
        return False
    if adolescente.get("lider_id") == usuario_id:
        return True
    lider_ga = obter_lider_ga_usuario()
    return bool(lider_ga) and adolescente.get("lider_id") is None and adolescente.get("lider_ga") == lider_ga


def adolescentes_disponiveis():
    if usuario_master():
        return Adolescente.listar_adolescentes()
    usuario_id = session.get("usuario_id")
    if not usuario_id:
        return []
    lider_ga = obter_lider_ga_usuario()
    adolescentes = Adolescente.listar_adolescentes(lider_id=usuario_id)
    if adolescentes:
        return adolescentes
    if lider_ga:
        return Adolescente.listar_adolescentes(lider_ga=lider_ga)
    return []


def obter_adolescente_com_permissao(adolescente_id):
    adolescente = Adolescente.obter_adolescente(adolescente_id)
    if not usuario_pode_acessar_adolescente(adolescente):
        return None
    return adolescente


def verificar_adolescente_do_formulario():
    adolescente_id = request.form.get("adolescente_id", "").strip()
    if not adolescente_id.isdigit():
        return None
    return obter_adolescente_com_permissao(int(adolescente_id))


def atividades_semana_fase1():
    ordem_codigos = ["P", "MV", "AB", "V"]
    ordem = {
        codigo: indice
        for indice, codigo in enumerate(ordem_codigos)
    }
    atividades = Atividade.listar_atividades(somente_ativas=True)
    filtradas = []
    for item in atividades:
        nome = normalizar_texto(item["nome"]).lower()
        for codigo in ordem_codigos:
            if nome in ATIVIDADES_FASE[codigo]["aliases"]:
                novo = dict(item)
                novo["codigo"] = codigo
                novo["pontos"] = ATIVIDADES_FASE[codigo]["pontos"]
                filtradas.append(novo)
                break
    filtradas.sort(key=lambda item: ordem.get(item["codigo"], 99))
    return filtradas


def montar_contexto_lancamento_fase1(adolescente_id=None):
    adolescentes = adolescentes_disponiveis()
    adolescente_selecionado = None
    semanas = [{"nome": nome, "data": data} for nome, data in FASE1_SEMANAS]
    datas_fase = [item["data"] for item in semanas]
    semana_atividades = atividades_semana_fase1()
    pontos_atividade = {item["id"]: item["pontos"] for item in semana_atividades}
    apps_atividade = Atividade.obter_id_atividade_por_nome("APPS")
    semana_marcacoes = {item["data"]: set() for item in semanas}
    pontos_por_semana = {item["data"]: 0 for item in semanas}
    apps_marcacoes = {}
    pontuacao_adolescente = None

    if adolescente_id:
        adolescente_selecionado = next((item for item in adolescentes if item["id"] == adolescente_id), None)
        if adolescente_selecionado:
            registros = Atividade.listar_cumprimentos_por_adolescente_datas(adolescente_id, datas_fase)
            for registro in registros:
                data_cumprimento = registro["data_cumprimento"]
                if apps_atividade and registro["atividade_id"] == apps_atividade:
                    if data_cumprimento not in apps_marcacoes or registro["id"] > apps_marcacoes[data_cumprimento]["id"]:
                        apps_marcacoes[data_cumprimento] = registro
                elif registro["cumpriu"] and data_cumprimento in semana_marcacoes:
                    semana_marcacoes[data_cumprimento].add(registro["atividade_id"])

            for data_ref, marcadas in semana_marcacoes.items():
                pontos_por_semana[data_ref] = sum(
                    pontos_atividade.get(atividade_id, 0) for atividade_id in marcadas
                )

            mapa_ranking = {item["id"]: item for item in Pontuacao.ranking_geral()}
            pontuacao_adolescente = mapa_ranking.get(adolescente_id)

    return {
        "adolescentes": adolescentes,
        "adolescente_selecionado": adolescente_selecionado,
        "semanas_fase1": semanas,
        "semana_atividades": semana_atividades,
        "apps_id": apps_atividade,
        "semana_marcacoes": semana_marcacoes,
        "pontos_por_semana": pontos_por_semana,
        "apps_marcacoes": apps_marcacoes,
        "pontuacao_adolescente": pontuacao_adolescente,
    }


def filtrar_ranking_por_permissao(ranking):
    if usuario_master():
        return list(ranking)
    lider_ga = obter_lider_ga_usuario()
    if not lider_ga:
        return []
    return [item for item in ranking if item["lider_ga"] == lider_ga]


def ranking_por_genero_de_lista(ranking):
    resultado = {"M": [], "F": []}
    for item in ranking:
        if item["sexo"] in resultado:
            resultado[item["sexo"]].append(item)
    return resultado


def filtrar_aniversariantes_por_permissao(aniversariantes):
    if usuario_master():
        return list(aniversariantes)
    lider_ga = obter_lider_ga_usuario()
    if not lider_ga:
        return []
    return [item for item in aniversariantes if item["lider_ga"] == lider_ga]


def filtrar_lideres_ativos_por_permissao(lista_lideres_ativos):
    if usuario_master():
        return list(lista_lideres_ativos)
    usuario_logado = session.get("usuario_id")
    return [item for item in lista_lideres_ativos if item["id"] == usuario_logado]


def montar_resumo_dashboard(ranking):
    return {
        "total_adolescentes": len(ranking),
        "total_pontos": sum(item["total_pontos"] for item in ranking),
        "lideres_ga": sorted({item["lider_ga"] for item in ranking if item["lider_ga"]}),
        "top_5": ranking[:5],
    }


def ranking_com_posicoes_por_pontos(ranking):
    lista = []
    posicao_atual = 0
    ultimo_total = None
    for item in ranking:
        total = item.get("total_pontos", 0)
        if ultimo_total is None or total != ultimo_total:
            posicao_atual += 1
            ultimo_total = total
        novo = dict(item)
        novo["posicao"] = posicao_atual
        lista.append(novo)
    return lista


def _nome_atividade_para_codigo(nome):
    nome_normalizado = normalizar_texto(nome).lower()
    for codigo, dados in ATIVIDADES_FASE.items():
        if nome_normalizado in dados["aliases"]:
            return codigo
    return None


def _resumo_atividades_por_adolescente():
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT ct.adolescente_id, a.nome AS atividade_nome
            FROM cumprimentos_tarefas ct
            JOIN atividades a ON a.id = ct.atividade_id
            WHERE ct.cumpriu = 1
            """
        ).fetchall()

    mapa = {}
    for row in rows:
        codigo = _nome_atividade_para_codigo(row["atividade_nome"])
        if not codigo:
            continue
        adolescente_id = row["adolescente_id"]
        mapa.setdefault(adolescente_id, set()).add(codigo)
    return mapa


def lider_master_autorizado():
    return bool(session.get("lider_master_autorizado"))


def listar_lideres_para_mensagem():
    with get_connection() as connection:
        return connection.execute(
            """
            SELECT id, nome, lider_ga
            FROM usuarios
            WHERE role = 'LIDER' AND aprovado = 1
            ORDER BY lider_ga, nome
            """
        ).fetchall()


def enviar_mensagem_para_lider(lider_id, mensagem):
    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO mensagens_master (lider_id, mensagem)
            VALUES (%s, %s)
            """,
            (int(lider_id), (mensagem or "").strip()),
        )


def listar_mensagens_do_lider(lider_id):
    with get_connection() as connection:
        return connection.execute(
            """
            SELECT id, mensagem, criado_em
            FROM mensagens_master
            WHERE lider_id = %s
            ORDER BY criado_em DESC, id DESC
            """,
            (int(lider_id),),
        ).fetchall()


def dados_painel_lider_master():
    ranking = Pontuacao.ranking_geral()
    atividades_por_adolescente = _resumo_atividades_por_adolescente()
    ordem_codigos = ["P", "MV", "AB", "V", "APPS"]
    painel = []
    for item in ranking:
        feitos = atividades_por_adolescente.get(item["id"], set())
        atividades_feitas = [ATIVIDADES_FASE[codigo]["nome"] for codigo in ordem_codigos if codigo in feitos]
        atividades_nao_feitas = [ATIVIDADES_FASE[codigo]["nome"] for codigo in ordem_codigos if codigo not in feitos]
        painel.append(
            {
                "nome": item["nome"],
                "lider_ga": item["lider_ga"],
                "total_pontos": item["total_pontos"],
                "atividades_feitas": ", ".join(atividades_feitas) if atividades_feitas else "-",
                "atividades_nao_feitas": ", ".join(atividades_nao_feitas) if atividades_nao_feitas else "-",
            }
        )
    return painel


def _texto_pdf(valor, limite=60):
    texto = normalizar_texto(str(valor))
    if len(texto) > limite:
        texto = texto[: limite - 3] + "..."
    return texto.encode("latin-1", "replace").decode("latin-1")


def gerar_pdf_ranking(ranking):
    pdf = FPDF(orientation="P", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=10)
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 14)
    pdf.cell(0, 8, "Nova Teens - Ranking Geral", ln=1)
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(0, 6, f"Gerado em: {datetime.now().strftime('%d/%m/%Y %H:%M')}", ln=1)
    pdf.ln(2)

    headers = [("Posicao", 18), ("Nome", 68), ("GA", 40), ("Pontos", 30), ("Cupons", 28)]
    pdf.set_font("Helvetica", "B", 10)
    for titulo, largura in headers:
        pdf.cell(largura, 8, titulo, border=1, align="C")
    pdf.ln()

    pdf.set_font("Helvetica", "", 10)
    for item in ranking:
        pdf.cell(18, 7, _texto_pdf(f"{item['posicao']}o", 5), border=1, align="C")
        pdf.cell(68, 7, _texto_pdf(item["nome"], 34), border=1)
        pdf.cell(40, 7, _texto_pdf(item["lider_ga"], 20), border=1)
        pdf.cell(30, 7, _texto_pdf(item["total_pontos"], 8), border=1, align="C")
        pdf.cell(28, 7, _texto_pdf(item["cupons"], 5), border=1, align="C")
        pdf.ln()

    conteudo = pdf.output(dest="S")
    if isinstance(conteudo, str):
        return conteudo.encode("latin-1")
    return bytes(conteudo)


def registrar_sessao(usuario):
    session.clear()
    session["usuario_id"] = usuario["id"]
    session["usuario_nome"] = usuario["nome"]
    session["usuario_role"] = usuario["role"]
    session["usuario_lider_ga"] = usuario["lider_ga"] or ""
    session.permanent = True


def listar_usuarios_pendentes():
    with get_connection() as connection:
        return connection.execute(
            """
            SELECT *
            FROM usuarios
            WHERE role = 'LIDER' AND aprovado = 0
            ORDER BY criado_em ASC
            """
        ).fetchall()


def listar_usuarios_aprovados():
    with get_connection() as connection:
        return connection.execute(
            """
            SELECT *
            FROM usuarios
            WHERE aprovado = 1
            ORDER BY
                CASE WHEN role = 'MASTER' THEN 0 ELSE 1 END,
                nome
            """
        ).fetchall()


def contar_masters():
    with get_connection() as connection:
        row = connection.execute(
            """
            SELECT COUNT(*) AS total
            FROM usuarios
            WHERE aprovado = 1 AND role = 'MASTER'
            """
        ).fetchone()
    return row["total"]


def registrar_auditoria(tipo_evento, alvo_tipo, alvo_id=None, detalhes=""):
    usuario_id = session.get("usuario_id")
    if not usuario_id:
        return

    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO auditoria_eventos (usuario_id, tipo_evento, alvo_tipo, alvo_id, detalhes)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (
                usuario_id,
                tipo_evento,
                alvo_tipo,
                alvo_id,
                (detalhes or "").strip()[:500],
            ),
        )


@app.context_processor
def inject_today():
    return {
        "today": date.today().isoformat(),
        "max_upload_mb": MAX_UPLOAD_MB,
        "csrf_token": gerar_csrf_token,
        "usuario_master": usuario_master,
        "lider_master_autorizado": lider_master_autorizado,
    }


@app.before_request
def proteger_formularios():
    if request.method == "POST" and not csrf_valido():
        flash("Sessão inválida. Tente enviar o formulário novamente.", "danger")
        return redirect(request.referrer or url_for("login"))


@app.after_request
def aplicar_headers_seguranca(response):
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "style-src 'self'; "
        "img-src 'self' data:; "
        "font-src 'self'; "
        "script-src 'self'; "
        "base-uri 'self'; "
        "form-action 'self'; "
        "frame-ancestors 'none'"
    )
    return response


@app.route("/")
def index():
    if "usuario_id" in session:
        return redirect(url_for("listar_adolescentes"))
    return redirect(url_for("login"))


@app.route("/cadastro", methods=["GET", "POST"])
def cadastro_usuario():
    if request.method == "POST":
        erro = validar_cadastro_usuario(request.form)
        if erro:
            flash(erro, "danger")
        else:
            nome = normalizar_texto(request.form["nome"])
            aniversario = request.form["aniversario"]
            lider_ga = normalizar_texto(request.form["lider_ga"])
            username_base = nome_slug(nome)[:20] or "lider"
            username = f"{username_base}-{secrets.token_hex(3)}"

            with get_connection() as connection:
                existente = connection.execute(
                    "SELECT id FROM usuarios WHERE lower(nome) = lower(%s)",
                    (nome,),
                ).fetchone()
                if existente:
                    flash("Já existe líder cadastrado com esse nome. Use outro nome ou ajuste na escrita.", "danger")
                else:
                    connection.execute(
                        """
                        INSERT INTO usuarios (
                            nome, contato, aniversario, username, senha_hash, role, aprovado, lider_ga
                        )
                        VALUES (%s, %s, %s, %s, %s, 'LIDER', 1, %s)
                        """,
                        (
                            nome,
                            "",
                            aniversario,
                            username,
                            generate_password_hash(request.form["senha"]),
                            lider_ga,
                        ),
                    )
                    flash("Cadastro criado com sucesso. Faça login para entrar.", "success")
                    return redirect(url_for("login"))

    return render_template("cadastro_usuario.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        identificador = normalizar_texto(request.form.get("nome", ""))
        senha = request.form.get("senha", "")

        with get_connection() as connection:
            usuario = connection.execute(
                "SELECT * FROM usuarios WHERE lower(nome) = lower(%s)",
                (identificador,),
            ).fetchone()
            if usuario is None:
                usuario = connection.execute(
                    "SELECT * FROM usuarios WHERE username = %s",
                    (identificador.lower(),),
                ).fetchone()

        if usuario and check_password_hash(usuario["senha_hash"], senha):
            with get_connection() as connection:
                connection.execute(
                    """
                    UPDATE usuarios
                    SET tentativas_falhas = 0, bloqueado_ate = NULL
                    WHERE id = %s
                    """,
                    (usuario["id"],),
                )
            registrar_sessao(usuario)
            flash("Login realizado com sucesso.", "success")
            return redirect(url_for("listar_adolescentes"))

        flash("Nome ou senha inválidos.", "danger")

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("Sessão encerrada.", "info")
    return redirect(url_for("login"))


@app.route("/usuarios/aprovacoes")
@master_obrigatorio
def usuarios_aprovacoes():
    return render_template(
        "usuarios_aprovacoes.html",
        usuarios_pendentes=listar_usuarios_pendentes(),
        usuarios_aprovados=listar_usuarios_aprovados(),
        total_masters=contar_masters(),
    )


@app.route("/usuarios/<int:usuario_id>/aprovar", methods=["POST"])
@master_obrigatorio
def aprovar_usuario(usuario_id):
    with get_connection() as connection:
        connection.execute(
            """
            UPDATE usuarios
            SET aprovado = 1
            WHERE id = %s AND role = 'LIDER'
            """,
            (usuario_id,),
        )
    registrar_auditoria("aprovacao_usuario", "usuario", usuario_id, "Conta aprovada pelo master.")
    flash("Conta aprovada com sucesso.", "success")
    return redirect(url_for("usuarios_aprovacoes"))


@app.route("/usuarios/<int:usuario_id>/rejeitar", methods=["POST"])
@master_obrigatorio
def rejeitar_usuario(usuario_id):
    with get_connection() as connection:
        connection.execute(
            "DELETE FROM usuarios WHERE id = %s AND role = 'LIDER' AND aprovado = 0",
            (usuario_id,),
        )
    registrar_auditoria("rejeicao_usuario", "usuario", usuario_id, "Solicitação rejeitada pelo master.")
    flash("Solicitação removida com sucesso.", "info")
    return redirect(url_for("usuarios_aprovacoes"))


@app.route("/usuarios/<int:usuario_id>/promover-master", methods=["POST"])
@master_obrigatorio
def promover_master(usuario_id):
    with get_connection() as connection:
        usuario = connection.execute(
            "SELECT * FROM usuarios WHERE id = %s",
            (usuario_id,),
        ).fetchone()

        if usuario is None or not usuario["aprovado"]:
            flash("Usuário não encontrado ou ainda não aprovado.", "danger")
        elif usuario["role"] == "MASTER":
            flash("Esse usuário já é master.", "warning")
        else:
            connection.execute(
                """
                UPDATE usuarios
                SET role = 'MASTER'
                WHERE id = %s
                """,
                (usuario_id,),
            )
            registrar_auditoria(
                "promocao_master",
                "usuario",
                usuario_id,
                f"{usuario['nome']} agora é master.",
            )
            flash("Usuário promovido para master com sucesso.", "success")

    return redirect(url_for("usuarios_aprovacoes"))


@app.route("/usuarios/<int:usuario_id>/remover-master", methods=["POST"])
@master_obrigatorio
def remover_master(usuario_id):
    with get_connection() as connection:
        usuario = connection.execute(
            "SELECT * FROM usuarios WHERE id = %s",
            (usuario_id,),
        ).fetchone()

        if usuario is None or not usuario["aprovado"]:
            flash("Usuário não encontrado ou ainda não aprovado.", "danger")
        elif usuario["role"] != "MASTER":
            flash("Esse usuário já está como líder.", "warning")
        elif contar_masters() <= 1:
            flash("É obrigatório manter pelo menos um usuário master ativo.", "danger")
        else:
            connection.execute(
                """
                UPDATE usuarios
                SET role = 'LIDER'
                WHERE id = %s
                """,
                (usuario_id,),
            )
            registrar_auditoria(
                "rebaixamento_master",
                "usuario",
                usuario_id,
                f"{usuario['nome']} voltou para líder.",
            )

            if session.get("usuario_id") == usuario_id:
                session["usuario_role"] = "LIDER"
                session["usuario_lider_ga"] = usuario["lider_ga"] or ""

            flash("Usuário voltou para o perfil de líder.", "info")

    return redirect(url_for("usuarios_aprovacoes"))


@app.route("/usuarios/<int:usuario_id>/definir-ga", methods=["POST"])
@master_obrigatorio
def definir_ga_usuario(usuario_id):
    ga = normalizar_texto(request.form.get("lider_ga", ""))
    erro = validar_lider_ga(ga)
    if erro:
        flash(erro, "danger")
        return redirect(url_for("usuarios_aprovacoes"))

    with get_connection() as connection:
        usuario = connection.execute(
            "SELECT * FROM usuarios WHERE id = %s AND aprovado = 1",
            (usuario_id,),
        ).fetchone()
        if usuario is None:
            flash("Usuário não encontrado.", "danger")
            return redirect(url_for("usuarios_aprovacoes"))

        connection.execute(
            """
            UPDATE usuarios
            SET lider_ga = %s
            WHERE id = %s
            """,
            (ga, usuario_id),
        )

    if session.get("usuario_id") == usuario_id:
        session["usuario_lider_ga"] = ga

    registrar_auditoria("definicao_ga_usuario", "usuario", usuario_id, f"GA definido como {ga}.")
    flash("GA do usuário atualizado com sucesso.", "success")
    return redirect(url_for("usuarios_aprovacoes"))


@app.route("/seguranca/senha", methods=["GET", "POST"])
@login_obrigatorio
def alterar_senha():
    if request.method == "POST":
        erro = validar_troca_senha(request.form)
        if erro:
            flash(erro, "danger")
        else:
            with get_connection() as connection:
                usuario = connection.execute(
                    "SELECT * FROM usuarios WHERE id = %s",
                    (session["usuario_id"],),
                ).fetchone()

                if not usuario or not check_password_hash(usuario["senha_hash"], request.form["senha_atual"]):
                    flash("A senha atual está incorreta.", "danger")
                else:
                    connection.execute(
                        """
                        UPDATE usuarios
                        SET senha_hash = %s
                        WHERE id = %s
                        """,
                        (generate_password_hash(request.form["nova_senha"]), usuario["id"]),
                    )
                    flash("Senha alterada com sucesso.", "success")
                    return redirect(url_for("dashboard"))

    return render_template("seguranca_senha.html")


@app.route("/perfil", methods=["GET", "POST"])
@login_obrigatorio
def editar_meu_cadastro():
    with get_connection() as connection:
        usuario = connection.execute(
            "SELECT * FROM usuarios WHERE id = %s",
            (session["usuario_id"],),
        ).fetchone()

        if usuario is None:
            session.clear()
            flash("Sessão expirada. Faça login novamente.", "warning")
            return redirect(url_for("login"))

        if request.method == "POST":
            action = request.form.get("action", "").strip()
            if action == "senha":
                nova_senha = request.form.get("nova_senha", "")
                erro = validar_password_forte(nova_senha)
                if erro:
                    flash(erro, "danger")
                else:
                    connection.execute(
                        """
                        UPDATE usuarios
                        SET senha_hash = %s
                        WHERE id = %s
                        """,
                        (generate_password_hash(nova_senha), usuario["id"]),
                    )
                    flash("Senha atualizada com sucesso.", "success")
                    return redirect(url_for("configuracoes"))
            else:
                erro = validar_atualizacao_perfil(request.form)
                if erro:
                    flash(erro, "danger")
                else:
                    nome = normalizar_texto(request.form["nome"])
                    novo_ga = normalizar_texto(request.form["lider_ga"])
                    ga_antigo = usuario["lider_ga"] or ""

                    connection.execute(
                        """
                        UPDATE usuarios
                        SET nome = %s, lider_ga = %s
                        WHERE id = %s
                        """,
                        (nome, novo_ga, usuario["id"]),
                    )
                    connection.execute(
                        """
                        UPDATE adolescentes
                        SET lider_ga = %s, lider_id = %s
                        WHERE lider_id = %s
                        """,
                        (novo_ga, usuario["id"], usuario["id"]),
                    )
                    if ga_antigo:
                        connection.execute(
                            """
                            UPDATE adolescentes
                            SET lider_ga = %s, lider_id = %s
                            WHERE lider_id IS NULL AND lower(lider_ga) = lower(%s)
                            """,
                            (novo_ga, usuario["id"], ga_antigo),
                        )

                    session["usuario_nome"] = nome
                    session["usuario_lider_ga"] = novo_ga
                    flash("Configurações atualizadas com sucesso.", "success")
                    return redirect(url_for("configuracoes"))

    return render_template("perfil_usuario.html", usuario=usuario)


@app.route("/configuracoes", methods=["GET", "POST"])
@login_obrigatorio
def configuracoes():
    return editar_meu_cadastro()


@app.route("/dashboard")
@login_obrigatorio
def dashboard():
    return redirect(url_for("listar_adolescentes"))


@app.route("/adolescentes")
@login_obrigatorio
def listar_adolescentes():
    busca = normalizar_texto(request.args.get("busca", ""))
    usuario_id = session.get("usuario_id")
    lider_ga = obter_lider_ga_usuario()
    if not lider_ga:
        flash("Defina o nome do GA nas Configurações para começar.", "warning")
    if usuario_master():
        adolescentes_raw = Adolescente.listar_adolescentes(busca=busca)
    else:
        adolescentes_raw = Adolescente.listar_adolescentes(
            busca=busca,
            lider_id=usuario_id,
        )
    adolescentes = []
    pontuacao_por_id = {item["id"]: item for item in Pontuacao.ranking_geral()}
    for adolescente in adolescentes_raw:
        item = dict(adolescente)
        item["idade"] = idade_por_data_iso(item.get("nascimento"))
        item["aniversario_curto"] = aniversario_curto(item.get("nascimento"))
        item["foto_path"] = item.get("foto_path", "")
        pontuacao = pontuacao_por_id.get(item["id"], {})
        item["pontuacao_total"] = pontuacao.get("total_pontos", 0)
        item["cupons"] = pontuacao.get("cupons", 0)
        adolescentes.append(item)
    return render_template(
        "adolescentes/lista.html",
        adolescentes=adolescentes,
        lideres=[],
        filtros={"busca": busca, "lider_ga": lider_ga, "sexo": ""},
    )


@app.route("/adolescentes/novo", methods=["GET", "POST"])
@login_obrigatorio
def novo_adolescente():
    if not lider_ga_configurado():
        flash("Defina o nome do GA nas Configurações para cadastrar adolescentes.", "warning")
        return redirect(url_for("listar_adolescentes"))

    if request.method == "POST":
        erro = validar_campos_adolescente(request.form)
        foto_path = ""
        if not erro:
            foto_path, erro_upload = salvar_foto_adolescente(
                request.files.get("foto"),
                request.form.get("nome", "adolescente"),
            )
            if foto_path is None:
                erro = mensagem_erro_upload_foto(erro_upload)
            elif not foto_path:
                erro = "A foto do adolescente é obrigatória."
        if erro:
            flash(erro, "danger")
        else:
            dados = dict(request.form)
            dados["lider_ga"] = obter_lider_ga_usuario()
            dados["lider_id"] = session.get("usuario_id")
            dados["foto_path"] = foto_path
            adolescente = Adolescente.cadastrar_adolescente(dados)
            registrar_auditoria(
                "cadastro_adolescente",
                "adolescente",
                adolescente["id"],
                f"Matrícula {adolescente['matricula']}.",
            )
            flash(f"Adolescente cadastrado com matrícula {adolescente['matricula']}.", "success")
            return redirect(url_for("listar_adolescentes"))
    return render_template("adolescentes/formulario.html", adolescente=None)


@app.route("/adolescentes/<int:adolescente_id>/editar", methods=["GET", "POST"])
@login_obrigatorio
def editar_adolescente(adolescente_id):
    adolescente = obter_adolescente_com_permissao(adolescente_id)
    if adolescente is None:
        flash("Adolescente não encontrado ou sem permissão de acesso.", "danger")
        return redirect(url_for("listar_adolescentes"))

    if request.method == "POST":
        erro = validar_campos_adolescente(request.form)
        foto_path = adolescente.get("foto_path", "")
        nova_foto = request.files.get("foto")
        if not erro and nova_foto and nova_foto.filename:
            foto_salva, erro_upload = salvar_foto_adolescente(
                nova_foto,
                request.form.get("nome", adolescente["nome"]),
            )
            if foto_salva is None:
                erro = mensagem_erro_upload_foto(erro_upload)
            else:
                foto_path = foto_salva
        if erro:
            flash(erro, "danger")
        else:
            dados = dict(request.form)
            dados["lider_ga"] = adolescente["lider_ga"] if usuario_master() else obter_lider_ga_usuario()
            dados["lider_id"] = adolescente.get("lider_id") or session.get("usuario_id")
            dados["foto_path"] = foto_path
            Adolescente.atualizar_adolescente(adolescente_id, dados)
            registrar_auditoria(
                "edicao_adolescente",
                "adolescente",
                adolescente_id,
                f"Cadastro de {adolescente['nome']} atualizado.",
            )
            flash("Cadastro atualizado com sucesso.", "success")
            return redirect(url_for("listar_adolescentes"))

    return render_template("adolescentes/formulario.html", adolescente=adolescente)


@app.route("/adolescentes/<int:adolescente_id>/excluir", methods=["POST"])
@login_obrigatorio
def excluir_adolescente(adolescente_id):
    adolescente = obter_adolescente_com_permissao(adolescente_id)
    if adolescente is None:
        flash("Adolescente não encontrado ou sem permissão de acesso.", "danger")
        return redirect(url_for("listar_adolescentes"))
    registrar_auditoria(
        "exclusao_adolescente",
        "adolescente",
        adolescente_id,
        f"Exclusão de {adolescente['nome']}.",
    )
    Adolescente.excluir_adolescente(adolescente_id)
    flash("Adolescente excluído com sucesso.", "info")
    return redirect(url_for("listar_adolescentes"))


@app.route("/adolescentes/<int:adolescente_id>", methods=["GET", "POST"])
@login_obrigatorio
def detalhe_adolescente(adolescente_id):
    adolescente = obter_adolescente_com_permissao(adolescente_id)
    if adolescente is None:
        flash("Adolescente não encontrado ou sem permissão de acesso.", "danger")
        return redirect(url_for("listar_adolescentes"))

    ids = mapear_atividades_fixas_ids()
    datas_fase = [data for _, data in FASE1_SEMANAS]
    apps_data = FASE1_SEMANAS[-1][1]

    if request.method == "POST":
        action = request.form.get("action", "").strip()
        if action == "salvar_semana":
            semana_data = request.form.get("semana_data", "").strip()
            if semana_data not in DATAS_FASE1:
                flash("Semana inválida para a fase atual.", "danger")
                return redirect(url_for("detalhe_adolescente", adolescente_id=adolescente_id))

            selecionados = {item.strip().upper() for item in request.form.getlist("itens")}
            for codigo in ["P", "MV", "AB", "V"]:
                atividade_id = ids.get(codigo)
                if not atividade_id:
                    continue
                if codigo in selecionados:
                    Atividade.upsert_cumprimento(
                        {
                            "adolescente_id": adolescente_id,
                            "atividade_id": atividade_id,
                            "data_cumprimento": semana_data,
                            "cumpriu": "1",
                            "falta_justificada": "0",
                            "observacoes": "",
                        },
                    )
                else:
                    Atividade.excluir_cumprimento_por_chave(
                        adolescente_id,
                        atividade_id,
                        semana_data,
                    )
            flash("Pontuação da semana atualizada.", "success")
            return redirect(url_for("detalhe_adolescente", adolescente_id=adolescente_id))

        if action == "salvar_apps":
            atividade_apps_id = ids.get("APPS")
            if not atividade_apps_id:
                flash("Atividade APPS não encontrada.", "danger")
                return redirect(url_for("detalhe_adolescente", adolescente_id=adolescente_id))
            marcado = request.form.get("apps_marcado") == "1"
            for data_ref in datas_fase:
                Atividade.excluir_cumprimento_por_chave(
                    adolescente_id,
                    atividade_apps_id,
                    data_ref,
                )
            if marcado:
                Atividade.upsert_cumprimento(
                    {
                        "adolescente_id": adolescente_id,
                        "atividade_id": atividade_apps_id,
                        "data_cumprimento": apps_data,
                        "cumpriu": "1",
                        "falta_justificada": "0",
                        "observacoes": "",
                    },
                    apps_id=atividade_apps_id,
                )
            flash("APPS atualizado com sucesso.", "success")
            return redirect(url_for("detalhe_adolescente", adolescente_id=adolescente_id))

    registros = Atividade.listar_cumprimentos_por_adolescente_datas(adolescente_id, datas_fase)
    marcacoes_semana = {data: {"P": False, "MV": False, "AB": False, "V": False} for data in datas_fase}
    apps_marcado = False
    for registro in registros:
        if not registro["cumpriu"]:
            continue
        atividade_id = registro["atividade_id"]
        data_ref = registro["data_cumprimento"]
        for codigo in ["P", "MV", "AB", "V"]:
            if ids.get(codigo) == atividade_id and data_ref in marcacoes_semana:
                marcacoes_semana[data_ref][codigo] = True
        if ids.get("APPS") == atividade_id and data_ref in DATAS_FASE1:
            apps_marcado = True

    pontuacao = Pontuacao.resumo_adolescente(adolescente_id)
    return render_template(
        "adolescentes/detalhe.html",
        adolescente=adolescente,
        pontuacao=pontuacao,
        semanas_fase1=FASE1_SEMANAS,
        marcacoes_semana=marcacoes_semana,
        apps_marcado=apps_marcado,
    )


@app.route("/atividades")
@login_obrigatorio
def listar_atividades():
    atividades = Atividade.listar_atividades(somente_ativas=True)
    return render_template("atividades/lista.html", atividades=atividades)


@app.route("/atividades/nova", methods=["GET", "POST"])
@master_obrigatorio
def nova_atividade():
    if request.method == "POST":
        erro = validar_campos_atividade(request.form)
        if erro:
            flash(erro, "danger")
        else:
            Atividade.cadastrar_atividade(request.form)
            flash("Atividade cadastrada com sucesso.", "success")
            return redirect(url_for("listar_atividades"))
    return render_template("atividades/formulario.html", atividade=None)


@app.route("/atividades/<int:atividade_id>/editar", methods=["GET", "POST"])
@master_obrigatorio
def editar_atividade(atividade_id):
    atividade = Atividade.obter_atividade(atividade_id)
    if atividade is None:
        flash("Atividade não encontrada.", "danger")
        return redirect(url_for("listar_atividades"))

    if request.method == "POST":
        erro = validar_campos_atividade(request.form)
        if erro:
            flash(erro, "danger")
        else:
            Atividade.atualizar_atividade(atividade_id, request.form)
            flash("Atividade atualizada com sucesso.", "success")
            return redirect(url_for("listar_atividades"))

    return render_template("atividades/formulario.html", atividade=atividade)


@app.route("/atividades/<int:atividade_id>/excluir", methods=["POST"])
@master_obrigatorio
def excluir_atividade(atividade_id):
    Atividade.excluir_atividade(atividade_id)
    flash("Atividade excluída com sucesso.", "info")
    return redirect(url_for("listar_atividades"))


@app.route("/cumprimentos")
@login_obrigatorio
def listar_cumprimentos():
    busca = normalizar_texto(request.args.get("busca", ""))
    adolescente_id_param = request.args.get("adolescente_id", "").strip()
    data_param = request.args.get("data_cumprimento", "").strip()

    adolescentes = adolescentes_disponiveis()
    ids_permitidos = {item["id"] for item in adolescentes}
    adolescentes_por_id = {item["id"]: item for item in adolescentes}
    cumprimentos = [item for item in Atividade.listar_cumprimentos() if item["adolescente_id"] in ids_permitidos]

    if busca:
        termo = busca.lower()
        adolescentes = [item for item in adolescentes if termo in item["nome"].lower()]

    registros_por_adolescente = {}
    for item in cumprimentos:
        registros_por_adolescente.setdefault(item["adolescente_id"], []).append(item)

    adolescentes_resumo = []
    for adolescente in adolescentes:
        registros = registros_por_adolescente.get(adolescente["id"], [])
        datas_unicas = sorted({item["data_cumprimento"] for item in registros}, reverse=True)
        adolescentes_resumo.append(
            {
                "id": adolescente["id"],
                "nome": adolescente["nome"],
                "matricula": adolescente["matricula"],
                "total_registros": len(registros),
                "total_datas": len(datas_unicas),
            }
        )

    adolescente_selecionado = None
    datas_lancamentos = []
    lancamentos_da_data = []

    if adolescente_id_param.isdigit():
        adolescente_id = int(adolescente_id_param)
        if adolescente_id in ids_permitidos:
            adolescente_selecionado = adolescentes_por_id.get(adolescente_id)
            registros_adolescente = [item for item in cumprimentos if item["adolescente_id"] == adolescente_id]
            datas = sorted({item["data_cumprimento"] for item in registros_adolescente}, reverse=True)
            datas_lancamentos = [
                {
                    "data_cumprimento": data_item,
                    "total_itens": sum(1 for item in registros_adolescente if item["data_cumprimento"] == data_item),
                }
                for data_item in datas
            ]
            if data_param:
                lancamentos_da_data = [
                    item for item in registros_adolescente if item["data_cumprimento"] == data_param
                ]

    return render_template(
        "cumprimentos/lista.html",
        adolescentes=adolescentes_resumo,
        adolescente_selecionado=adolescente_selecionado,
        datas_lancamentos=datas_lancamentos,
        lancamentos_da_data=lancamentos_da_data,
        filtros={"busca": busca, "adolescente_id": adolescente_id_param, "data_cumprimento": data_param},
    )


@app.route("/cumprimentos/novo", methods=["GET", "POST"])
@login_obrigatorio
def novo_cumprimento():
    adolescente_id_param = request.args.get("adolescente_id", "").strip()
    adolescente_id = int(adolescente_id_param) if adolescente_id_param.isdigit() else None
    contexto = montar_contexto_lancamento_fase1(adolescente_id=adolescente_id)

    if request.method == "POST":
        adolescente = verificar_adolescente_do_formulario()
        if adolescente is None:
            flash("Você não tem permissão para lançar tarefas para este adolescente.", "danger")
            return redirect(url_for("novo_cumprimento"))

        adolescente_id = adolescente["id"]
        action = request.form.get("action", "").strip()
        apps_id = contexto["apps_id"]
        atividades_semana = {item["id"] for item in contexto["semana_atividades"]}
        datas_fase = {data for _, data in FASE1_SEMANAS}

        if action == "salvar_semana":
            semana_data = request.form.get("semana_data", "").strip()
            if semana_data not in datas_fase:
                flash("Data de semana inválida para a fase 1.", "danger")
                return redirect(url_for("novo_cumprimento", adolescente_id=adolescente_id))

            ids_selecionados = {
                int(item)
                for item in request.form.getlist("atividade_ids")
                if item.isdigit()
            }
            ids_validos = ids_selecionados.intersection(atividades_semana)
            if not ids_validos:
                flash("Selecione ao menos uma atividade para salvar na semana.", "warning")
                return redirect(url_for("novo_cumprimento", adolescente_id=adolescente_id))

            registros = []
            for atividade_id in ids_validos:
                registro = Atividade.upsert_cumprimento(
                    {
                        "adolescente_id": adolescente_id,
                        "atividade_id": atividade_id,
                        "data_cumprimento": semana_data,
                        "cumpriu": "1",
                        "falta_justificada": "0",
                        "observacoes": "",
                    },
                    apps_id=apps_id,
                )
                registros.append(registro)

            for registro in registros:
                registrar_auditoria(
                    "lancamento_cumprimento",
                    "cumprimento",
                    registro["id"],
                    f"Lançamento semanal para {adolescente['nome']}.",
                )
            flash("Semana salva com sucesso. Você pode voltar e adicionar atividades esquecidas quando precisar.", "success")
            return redirect(url_for("novo_cumprimento", adolescente_id=adolescente_id))

        if action == "salvar_apps":
            if not apps_id:
                flash("Atividade APPS não encontrada.", "danger")
                return redirect(url_for("novo_cumprimento", adolescente_id=adolescente_id))

            registros = []
            for _, data_apps in FASE1_SEMANAS:
                if request.form.get(f"apps_lancar_{data_apps}") != "1":
                    continue

                cumpriu = request.form.get(f"apps_cumpriu_{data_apps}", "1")
                falta_justificada = request.form.get(f"apps_falta_justificada_{data_apps}", "0")
                if cumpriu not in {"0", "1"}:
                    continue

                if Atividade.existe_cumprimento_no_dia(adolescente_id, apps_id, data_apps):
                    flash(
                        f"O APPS de {data_apps} já foi lançado. Edite no histórico de cumprimentos.",
                        "warning",
                    )
                    continue

                registro = Atividade.registrar_cumprimento(
                    {
                        "adolescente_id": adolescente_id,
                        "atividade_id": apps_id,
                        "data_cumprimento": data_apps,
                        "cumpriu": cumpriu,
                        "falta_justificada": falta_justificada,
                        "observacoes": "",
                    },
                    apps_id=apps_id,
                )
                registros.append(registro)

            for registro in registros:
                registrar_auditoria(
                    "lancamento_cumprimento",
                    "cumprimento",
                    registro["id"],
                    f"Lançamento APPS para {adolescente['nome']}.",
                )
            if registros:
                flash("Lançamentos de APPS processados.", "success")
            else:
                flash("Nenhum lançamento novo de APPS foi salvo.", "warning")
            return redirect(url_for("novo_cumprimento", adolescente_id=adolescente_id))

        flash("Ação de lançamento inválida.", "danger")
        return redirect(url_for("novo_cumprimento", adolescente_id=adolescente_id))

    return render_template(
        "cumprimentos/formulario.html",
        cumprimento=None,
        adolescente_id=adolescente_id,
        **contexto,
    )


@app.route("/cumprimentos/<int:cumprimento_id>/editar", methods=["GET", "POST"])
@login_obrigatorio
def editar_cumprimento(cumprimento_id):
    cumprimento = Atividade.obter_cumprimento(cumprimento_id)
    if cumprimento is None or obter_adolescente_com_permissao(cumprimento["adolescente_id"]) is None:
        flash("Registro de cumprimento não encontrado ou sem permissão de acesso.", "danger")
        return redirect(url_for("listar_cumprimentos"))

    atividade_apps_id = Atividade.obter_id_atividade_por_nome("APPS")
    incluir_apps = bool(atividade_apps_id and cumprimento["atividade_id"] == atividade_apps_id)
    presenca_id = Atividade.obter_id_atividade_por_nome("Presença culto")
    datas_presenca_por_adolescente = (
        Atividade.mapa_datas_lancadas_por_atividade(presenca_id) if presenca_id else {}
    )
    datas_apps_por_adolescente = (
        Atividade.mapa_datas_lancadas_por_atividade(atividade_apps_id) if atividade_apps_id else {}
    )
    atividades_semana = atividades_semana_fase1()
    ids_atividades_semana = {item["id"] for item in atividades_semana}
    datas_fase1 = {item[1] for item in FASE1_SEMANAS}
    registros_mesma_data = Atividade.listar_cumprimentos_por_adolescente_datas(
        cumprimento["adolescente_id"], [cumprimento["data_cumprimento"]]
    )
    atividades_ja_lancadas_na_data = {item["atividade_id"] for item in registros_mesma_data}
    atividades_adicionaveis = [
        item for item in atividades_semana if item["id"] not in atividades_ja_lancadas_na_data
    ]
    mostrar_adicao_na_edicao = cumprimento["data_cumprimento"] in datas_fase1 and bool(atividades_adicionaveis)

    if request.method == "POST":
        action = request.form.get("action", "salvar_cumprimento").strip()
        if action == "adicionar_atividade_semana":
            adolescente = verificar_adolescente_do_formulario()
            if adolescente is None or adolescente["id"] != cumprimento["adolescente_id"]:
                flash("Você não tem permissão para ajustar essa semana deste adolescente.", "danger")
            elif cumprimento["data_cumprimento"] not in datas_fase1:
                flash("Adição rápida disponível apenas para semanas da Fase 1.", "warning")
            else:
                ids_selecionados = {
                    int(item)
                    for item in request.form.getlist("atividade_ids")
                    if item.isdigit()
                }
                ids_validos = ids_selecionados.intersection(ids_atividades_semana)
                if not ids_validos:
                    flash("Selecione ao menos uma atividade para adicionar nesta semana.", "warning")
                else:
                    for atividade_id in ids_validos:
                        registro = Atividade.upsert_cumprimento(
                            {
                                "adolescente_id": adolescente["id"],
                                "atividade_id": atividade_id,
                                "data_cumprimento": cumprimento["data_cumprimento"],
                                "cumpriu": "1",
                                "falta_justificada": "0",
                                "observacoes": "",
                            },
                            apps_id=atividade_apps_id,
                        )
                        registrar_auditoria(
                            "edicao_cumprimento",
                            "cumprimento",
                            registro["id"],
                            f"Atividade adicionada na semana para {adolescente['nome']}.",
                        )
                    flash("Atividades adicionadas na semana com sucesso.", "success")
                    return redirect(
                        url_for(
                            "listar_cumprimentos",
                            adolescente_id=adolescente["id"],
                            data_cumprimento=cumprimento["data_cumprimento"],
                        )
                    )
        else:
            erro = validar_campos_cumprimento(request.form)
            adolescente = verificar_adolescente_do_formulario()
            if erro:
                flash(erro, "danger")
            elif adolescente is None:
                flash("Você não tem permissão para lançar tarefa para este adolescente.", "danger")
            elif atividade_apps_id and request.form.get("atividade_id", "").isdigit() and int(request.form["atividade_id"]) == atividade_apps_id and not data_permitida_fase1_apps(request.form.get("data_cumprimento")):
                flash("Na 1ª fase do Top Teens, a atividade APPS só pode ser lançada em 15/03/2026, 22/03/2026, 29/03/2026 ou 12/04/2026.", "danger")
            elif atividade_apps_id and request.form.get("atividade_id", "").isdigit() and int(request.form["atividade_id"]) == atividade_apps_id and Atividade.existe_cumprimento_no_dia(
                request.form.get("adolescente_id"),
                atividade_apps_id,
                request.form.get("data_cumprimento", ""),
                excluir_id=cumprimento_id,
            ):
                flash("Esse adolescente já possui APPS lançado nessa data. Use o registro já existente.", "danger")
            elif presenca_id and request.form.get("atividade_id", "").isdigit() and int(request.form["atividade_id"]) == presenca_id and Atividade.existe_cumprimento_no_dia(
                request.form.get("adolescente_id"),
                presenca_id,
                request.form.get("data_cumprimento", ""),
                excluir_id=cumprimento_id,
            ):
                flash("Esse adolescente já possui presença lançada nessa data. Edite o registro existente.", "danger")
            else:
                Atividade.atualizar_cumprimento(
                    cumprimento_id,
                    request.form,
                    presenca_id=presenca_id,
                    apps_id=atividade_apps_id,
                )
                registrar_auditoria(
                    "edicao_cumprimento",
                    "cumprimento",
                    cumprimento_id,
                    f"Cumprimento ajustado para {adolescente['nome']}.",
                )
                flash("Cumprimento atualizado com sucesso.", "success")
                return redirect(url_for("listar_cumprimentos"))

    return render_template(
        "cumprimentos/formulario.html",
        cumprimento=cumprimento,
        adolescentes=adolescentes_disponiveis(),
        atividades=Atividade.listar_atividades(somente_ativas=True, incluir_apps=incluir_apps),
        presenca_id=presenca_id,
        apps_id=atividade_apps_id,
        datas_apps_fase=sorted(DATAS_FASE1_APPS),
        datas_presenca_por_adolescente=datas_presenca_por_adolescente,
        datas_apps_por_adolescente=datas_apps_por_adolescente,
        mostrar_adicao_na_edicao=mostrar_adicao_na_edicao,
        atividades_adicionaveis=atividades_adicionaveis,
    )


@app.route("/cumprimentos/<int:cumprimento_id>/excluir", methods=["POST"])
@login_obrigatorio
def excluir_cumprimento(cumprimento_id):
    cumprimento = Atividade.obter_cumprimento(cumprimento_id)
    if cumprimento is None or obter_adolescente_com_permissao(cumprimento["adolescente_id"]) is None:
        flash("Registro de cumprimento não encontrado ou sem permissão de acesso.", "danger")
        return redirect(url_for("listar_cumprimentos"))
    registrar_auditoria(
        "exclusao_cumprimento",
        "cumprimento",
        cumprimento_id,
        "Cumprimento excluído.",
    )
    Atividade.excluir_cumprimento(cumprimento_id)
    flash("Cumprimento excluído com sucesso.", "info")
    return redirect(url_for("listar_cumprimentos"))


@app.route("/ranking")
@login_obrigatorio
def ranking():
    ranking_atual = ranking_com_posicoes_por_pontos(Pontuacao.ranking_geral())
    return render_template(
        "ranking.html",
        ranking=ranking_atual,
    )


@app.route("/ranking/pdf")
@login_obrigatorio
def ranking_pdf():
    ranking_atual = ranking_com_posicoes_por_pontos(Pontuacao.ranking_geral())
    conteudo = gerar_pdf_ranking(ranking_atual)
    resposta = make_response(conteudo)
    resposta.headers["Content-Type"] = "application/pdf"
    resposta.headers["Content-Disposition"] = "attachment; filename=ranking-nova-teens.pdf"
    return resposta


@app.route("/lider-master", methods=["GET", "POST"])
@login_obrigatorio
def lider_master():
    if request.method == "POST":
        acao = request.form.get("acao", "autenticar").strip()
        if acao == "autenticar":
            senha_informada = request.form.get("senha_master", "")
            if secrets.compare_digest(senha_informada, SENHA_LIDER_MASTER):
                session["lider_master_autorizado"] = True
                flash("Acesso Líder Master liberado.", "success")
            else:
                session.pop("lider_master_autorizado", None)
                flash("Senha do Líder Master incorreta.", "danger")
            return redirect(url_for("lider_master"))

        if not lider_master_autorizado():
            flash("Informe a senha do Líder Master para acessar o painel.", "warning")
            return redirect(url_for("lider_master"))

        if acao == "encerrar":
            session.pop("lider_master_autorizado", None)
            flash("Acesso Líder Master encerrado.", "info")
            return redirect(url_for("lider_master"))

        if acao == "enviar_mensagem":
            lider_id_param = request.form.get("lider_id", "").strip()
            mensagem = (request.form.get("mensagem", "") or "").strip()
            if not lider_id_param.isdigit():
                flash("Selecione um líder válido.", "danger")
                return redirect(url_for("lider_master"))

            lider_id = int(lider_id_param)
            lideres = listar_lideres_para_mensagem()
            lider_existe = next((item for item in lideres if item["id"] == lider_id), None)
            if lider_existe is None:
                flash("Líder não encontrado.", "danger")
                return redirect(url_for("lider_master"))
            if not mensagem:
                flash("Digite a mensagem antes de enviar.", "danger")
                return redirect(url_for("lider_master", lider_id=lider_id))
            if len(mensagem) > 500:
                flash("A mensagem deve ter no máximo 500 caracteres.", "danger")
                return redirect(url_for("lider_master", lider_id=lider_id))

            enviar_mensagem_para_lider(lider_id, mensagem)
            flash("Mensagem enviada com sucesso.", "success")
            return redirect(url_for("lider_master", lider_id=lider_id))

    autorizado = lider_master_autorizado()
    lideres = listar_lideres_para_mensagem() if autorizado else []
    lider_selecionado = None
    lider_id_param = request.args.get("lider_id", "").strip()
    if autorizado and lider_id_param.isdigit():
        lider_id = int(lider_id_param)
        lider_selecionado = next((item for item in lideres if item["id"] == lider_id), None)

    painel = dados_painel_lider_master() if autorizado else []
    return render_template(
        "lider_master.html",
        autorizado=autorizado,
        lideres=lideres,
        lider_selecionado=lider_selecionado,
        adolescentes=painel,
    )


@app.route("/mensagens")
@login_obrigatorio
def mensagens():
    mensagens_lider = listar_mensagens_do_lider(session["usuario_id"])
    return render_template("mensagens.html", mensagens=mensagens_lider)


def preparar_aplicacao():
    init_db()
    criar_usuario_padrao()
    popular_atividades_iniciais()


preparar_aplicacao()


if __name__ == "__main__":
    host = environ.get("HOST", "127.0.0.1")
    port = int(environ.get("PORT", "5000"))
    app.run(host=host, port=port, debug=False)
