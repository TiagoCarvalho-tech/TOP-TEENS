from datetime import date, datetime, timedelta
from functools import wraps
from os import environ
from pathlib import Path
import re
import secrets

from flask import Flask, abort, flash, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

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
app.config["MAX_CONTENT_LENGTH"] = 1024 * 1024
DATAS_FASE1_APPS = {
    "2026-03-15",
    "2026-03-22",
    "2026-03-29",
    "2026-04-12",
}


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


def somente_letras_espacos(texto):
    return bool(re.fullmatch(r"[A-Za-zÀ-ÿ' -]+", texto))


def obter_lider_ga_usuario():
    return normalizar_texto(session.get("usuario_lider_ga", ""))


def data_permitida_fase1_apps(valor_data):
    if not valor_data:
        return False
    return valor_data in DATAS_FASE1_APPS


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
        ("Presença culto", 10, "Registrar presença no culto"),
        ("Meditação e versículo", 10, "Cumprir meditação e versículo da fase"),
        ("Bíblia e anotação", 10, "Leitura bíblica com anotação"),
        ("Visitante", 1, "Levar um visitante"),
        ("APPS", 40, "Pontuação de fase do APPS com regra de presença"),
        ("Não cumpriu nenhuma atividade", 0, "Lançamento sem pontuação"),
    ]
    aliases = {
        "Presença": "Presença culto",
        "Meditação": "Meditação e versículo",
        "Apps": "APPS",
    }
    nomes_oficiais = {nome.lower() for nome, _, _ in atividades_padrao}

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

        # Garante APPS como atividade ativa e com 40 pontos no formulário.
        connection.execute(
            """
            UPDATE atividades
            SET pontos = 40, ativo = 1
            WHERE lower(trim(nome)) = lower('APPS')
            """
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
        validar_contato(formulario.get("contato")),
        validar_nome_pessoa(formulario.get("responsavel"), "Nome do Responsável"),
        validar_lider_ga(formulario.get("lider_ga")),
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
    obrigatorios = ["adolescente_id", "data_cumprimento", "cumpriu"]
    if any(not formulario.get(campo, "").strip() for campo in obrigatorios):
        return "Preencha adolescente, data e status do cumprimento."
    atividade_ids = [item for item in request.form.getlist("atividade_ids") if item.strip()]
    if not atividade_ids:
        return "Selecione pelo menos uma atividade para lançar."
    if formulario.get("cumpriu") not in {"0", "1"}:
        return "Selecione um status válido para o cumprimento."
    if any(not atividade_id.isdigit() for atividade_id in atividade_ids):
        return "Há uma atividade inválida na seleção."

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
    aniversario = formulario.get("aniversario")

    erro_aniversario = None
    if not aniversario:
        erro_aniversario = "O campo Aniversário é obrigatório."
    else:
        erro_aniversario = validar_nascimento(aniversario)
        if erro_aniversario:
            erro_aniversario = erro_aniversario.replace("Data de nascimento", "Aniversário")

    for erro in [
        validar_nome_pessoa(formulario.get("nome"), "Nome"),
        "O campo Contato é obrigatório." if not normalizar_texto(formulario.get("contato")) else validar_contato(formulario.get("contato")),
        erro_aniversario,
    ]:
        if erro:
            return erro
    return None


def validar_cadastro_usuario(formulario):
    nome = normalizar_texto(formulario.get("nome"))
    contato = normalizar_texto(formulario.get("contato"))
    aniversario = formulario.get("aniversario")
    username = normalizar_texto(formulario.get("username")).lower()
    senha = formulario.get("senha", "")
    confirmar = formulario.get("confirmar_senha", "")

    erro_aniversario = None
    if not aniversario:
        erro_aniversario = "O campo Aniversário é obrigatório."
    else:
        erro_aniversario = validar_nascimento(aniversario)
        if erro_aniversario:
            erro_aniversario = erro_aniversario.replace("Data de nascimento", "Aniversário")

    for erro in [
        validar_nome_pessoa(nome, "Nome"),
        "O campo Contato é obrigatório." if not contato else validar_contato(contato),
        erro_aniversario,
    ]:
        if erro:
            return erro

    if not re.fullmatch(r"[a-z0-9._-]{4,30}", username):
        return "O usuário deve ter 4 a 30 caracteres com letras minúsculas, números, ponto, hífen ou sublinhado."
    erro_senha = validar_password_forte(senha)
    if erro_senha:
        return erro_senha
    if senha != confirmar:
        return "A confirmação da senha não confere."
    return None


def usuario_pode_acessar_adolescente(adolescente):
    return adolescente is not None


def adolescentes_disponiveis():
    return Adolescente.listar_adolescentes()


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
        "csrf_token": gerar_csrf_token,
        "usuario_master": usuario_master,
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
        return redirect(url_for("dashboard"))
    return redirect(url_for("login"))


@app.route("/cadastro", methods=["GET", "POST"])
def cadastro_usuario():
    if request.method == "POST":
        erro = validar_cadastro_usuario(request.form)
        if erro:
            flash(erro, "danger")
        else:
            nome = normalizar_texto(request.form["nome"])
            contato = Adolescente.normalizar_contato(request.form["contato"])
            aniversario = request.form["aniversario"]
            username = normalizar_texto(request.form["username"]).lower()

            with get_connection() as connection:
                existente = connection.execute(
                    "SELECT id FROM usuarios WHERE username = %s",
                    (username,),
                ).fetchone()
                if existente:
                    flash("Esse nome de usuário já está em uso.", "danger")
                else:
                    connection.execute(
                        """
                        INSERT INTO usuarios (
                            nome, contato, aniversario, username, senha_hash, role, aprovado, lider_ga
                        )
                        VALUES (%s, %s, %s, %s, %s, 'LIDER', 0, %s)
                        """,
                        (
                            nome,
                            contato,
                            aniversario,
                            username,
                            generate_password_hash(request.form["senha"]),
                            "",
                        ),
                    )
                    flash("Cadastro enviado com sucesso. Aguarde a aprovação do usuário master.", "success")
                    return redirect(url_for("login"))

    return render_template("cadastro_usuario.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = normalizar_texto(request.form.get("username", "")).lower()
        senha = request.form.get("senha", "")

        with get_connection() as connection:
            usuario = connection.execute(
                "SELECT * FROM usuarios WHERE username = %s",
                (username,),
            ).fetchone()

            if usuario and usuario["bloqueado_ate"]:
                bloqueado_ate = datetime.fromisoformat(usuario["bloqueado_ate"])
                if bloqueado_ate > datetime.now():
                    flash("Conta temporariamente bloqueada por tentativas inválidas. Tente novamente mais tarde.", "danger")
                    return render_template("login.html")

        if usuario and check_password_hash(usuario["senha_hash"], senha):
            if not usuario["aprovado"]:
                flash("Seu cadastro ainda está pendente de aprovação do usuário master.", "warning")
                return render_template("login.html")

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
            return redirect(url_for("dashboard"))

        if usuario:
            tentativas = usuario["tentativas_falhas"] + 1
            bloqueado_ate = None
            if tentativas >= 5:
                bloqueado_ate = (datetime.now() + timedelta(minutes=15)).isoformat(timespec="seconds")
                tentativas = 0

            with get_connection() as connection:
                connection.execute(
                    """
                    UPDATE usuarios
                    SET tentativas_falhas = %s, bloqueado_ate = %s
                    WHERE id = %s
                    """,
                    (tentativas, bloqueado_ate, usuario["id"]),
                )

        flash("Usuário ou senha inválidos.", "danger")

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
            erro = validar_atualizacao_perfil(request.form)
            if erro:
                flash(erro, "danger")
            else:
                nome = normalizar_texto(request.form["nome"])
                contato = Adolescente.normalizar_contato(request.form["contato"])
                aniversario = request.form["aniversario"]

                connection.execute(
                    """
                    UPDATE usuarios
                    SET nome = %s, contato = %s, aniversario = %s
                    WHERE id = %s
                    """,
                    (nome, contato, aniversario, usuario["id"]),
                )
                session["usuario_nome"] = nome
                registrar_auditoria("edicao_perfil", "usuario", usuario["id"], "Perfil atualizado pelo próprio usuário.")
                flash("Cadastro atualizado com sucesso.", "success")
                return redirect(url_for("dashboard"))

    return render_template("perfil_usuario.html", usuario=usuario)


@app.route("/dashboard")
@login_obrigatorio
def dashboard():
    resumo = Pontuacao.resumo_dashboard()
    aniversariantes = Adolescente.aniversariantes_proximos()
    ranking_genero = Pontuacao.ranking_por_sexo()
    lideres_mais_ativos = Pontuacao.ranking_lideres_mais_ativos()
    return render_template(
        "dashboard.html",
        resumo=resumo,
        aniversariantes=aniversariantes,
        ranking_genero=ranking_genero,
        lideres_mais_ativos=lideres_mais_ativos,
    )


@app.route("/adolescentes")
@login_obrigatorio
def listar_adolescentes():
    busca = normalizar_texto(request.args.get("busca", ""))
    lider_ga = normalizar_texto(request.args.get("lider_ga", ""))
    sexo = request.args.get("sexo", "").strip()

    adolescentes = Adolescente.listar_adolescentes(busca, lider_ga, sexo)
    lideres = Adolescente.listar_lideres_ga()
    return render_template(
        "adolescentes/lista.html",
        adolescentes=adolescentes,
        lideres=lideres,
        filtros={"busca": busca, "lider_ga": lider_ga, "sexo": sexo},
    )


@app.route("/adolescentes/novo", methods=["GET", "POST"])
@login_obrigatorio
def novo_adolescente():
    if request.method == "POST":
        erro = validar_campos_adolescente(request.form)
        if erro:
            flash(erro, "danger")
        else:
            dados = dict(request.form)
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
        if erro:
            flash(erro, "danger")
        else:
            dados = dict(request.form)
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


@app.route("/adolescentes/<int:adolescente_id>")
@login_obrigatorio
def detalhe_adolescente(adolescente_id):
    adolescente = obter_adolescente_com_permissao(adolescente_id)
    if adolescente is None:
        flash("Adolescente não encontrado ou sem permissão de acesso.", "danger")
        return redirect(url_for("listar_adolescentes"))

    cumprimentos = Atividade.listar_cumprimentos(adolescente_id)
    ranking = {item["id"]: item for item in Pontuacao.ranking_geral()}
    pontuacao = ranking.get(adolescente_id)
    return render_template(
        "adolescentes/detalhe.html",
        adolescente=adolescente,
        cumprimentos=cumprimentos,
        pontuacao=pontuacao,
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
    presenca_id = Atividade.obter_id_atividade_por_nome("Presença culto")
    apps_id = Atividade.obter_id_atividade_por_nome("APPS")
    datas_presenca_por_adolescente = (
        Atividade.mapa_datas_lancadas_por_atividade(presenca_id) if presenca_id else {}
    )
    datas_apps_por_adolescente = (
        Atividade.mapa_datas_lancadas_por_atividade(apps_id) if apps_id else {}
    )

    if request.method == "POST":
        erro = validar_campos_cumprimento_lote(request.form)
        adolescente = verificar_adolescente_do_formulario()
        if erro:
            flash(erro, "danger")
        elif adolescente is None:
            flash("Você não tem permissão para lançar tarefa para este adolescente.", "danger")
        else:
            atividade_ids = [item for item in request.form.getlist("atividade_ids") if item.strip()]
            atividade_ids_int = {int(item) for item in atividade_ids}
            if apps_id and apps_id in atividade_ids_int and not data_permitida_fase1_apps(request.form.get("data_cumprimento")):
                flash("Na 1ª fase do Top Teens, a atividade APPS só pode ser lançada em 15/03/2026, 22/03/2026, 29/03/2026 ou 12/04/2026.", "danger")
                return render_template(
                    "cumprimentos/formulario.html",
                    cumprimento=None,
                    adolescentes=adolescentes_disponiveis(),
                    atividades=Atividade.listar_atividades(somente_ativas=True),
                    presenca_id=presenca_id,
                    apps_id=apps_id,
                    datas_apps_fase=sorted(DATAS_FASE1_APPS),
                    datas_presenca_por_adolescente=datas_presenca_por_adolescente,
                    datas_apps_por_adolescente=datas_apps_por_adolescente,
                )
            if apps_id and apps_id in atividade_ids_int and Atividade.existe_cumprimento_no_dia(
                adolescente["id"],
                apps_id,
                request.form.get("data_cumprimento", ""),
            ):
                flash("Esse adolescente já possui APPS lançado nessa data. Use a edição no histórico de cumprimentos.", "danger")
                return render_template(
                    "cumprimentos/formulario.html",
                    cumprimento=None,
                    adolescentes=adolescentes_disponiveis(),
                    atividades=Atividade.listar_atividades(somente_ativas=True),
                    presenca_id=presenca_id,
                    apps_id=apps_id,
                    datas_apps_fase=sorted(DATAS_FASE1_APPS),
                    datas_presenca_por_adolescente=datas_presenca_por_adolescente,
                    datas_apps_por_adolescente=datas_apps_por_adolescente,
                )
            if presenca_id and presenca_id in atividade_ids_int and Atividade.existe_cumprimento_no_dia(
                adolescente["id"],
                presenca_id,
                request.form.get("data_cumprimento", ""),
            ):
                flash("Esse adolescente já possui presença lançada nessa data. Edite o registro existente.", "danger")
                return render_template(
                    "cumprimentos/formulario.html",
                    cumprimento=None,
                    adolescentes=adolescentes_disponiveis(),
                    atividades=Atividade.listar_atividades(somente_ativas=True),
                    presenca_id=presenca_id,
                    apps_id=apps_id,
                    datas_apps_fase=sorted(DATAS_FASE1_APPS),
                    datas_presenca_por_adolescente=datas_presenca_por_adolescente,
                    datas_apps_por_adolescente=datas_apps_por_adolescente,
                )

            registros = Atividade.registrar_cumprimentos_em_lote(request.form, atividade_ids, presenca_id=presenca_id)
            for registro in registros:
                registrar_auditoria(
                    "lancamento_cumprimento",
                    "cumprimento",
                    registro["id"],
                    f"Lançamento para {adolescente['nome']}.",
                )
            flash(f"{len(atividade_ids)} atividade(s) registrada(s) com sucesso.", "success")
            return redirect(url_for("listar_cumprimentos"))

    return render_template(
        "cumprimentos/formulario.html",
        cumprimento=None,
        adolescentes=adolescentes_disponiveis(),
        atividades=Atividade.listar_atividades(somente_ativas=True),
        presenca_id=presenca_id,
        apps_id=apps_id,
        datas_apps_fase=sorted(DATAS_FASE1_APPS),
        datas_presenca_por_adolescente=datas_presenca_por_adolescente,
        datas_apps_por_adolescente=datas_apps_por_adolescente,
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

    if request.method == "POST":
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
            Atividade.atualizar_cumprimento(cumprimento_id, request.form, presenca_id=presenca_id)
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
    return render_template(
        "ranking.html",
        ranking=Pontuacao.ranking_geral(),
        ranking_genero=Pontuacao.ranking_por_sexo(),
        lideres_mais_ativos=Pontuacao.ranking_lideres_mais_ativos(),
    )


def preparar_aplicacao():
    init_db()
    criar_usuario_padrao()
    popular_atividades_iniciais()


preparar_aplicacao()


if __name__ == "__main__":
    host = environ.get("HOST", "127.0.0.1")
    port = int(environ.get("PORT", "5000"))
    app.run(host=host, port=port, debug=False)
