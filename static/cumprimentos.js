(function () {
    function initBuscaAdolescente() {
        const camposBusca = Array.from(document.querySelectorAll("[data-adolescente-busca-for]"));
        camposBusca.forEach((campoBusca) => {
            const selectId = campoBusca.getAttribute("data-adolescente-busca-for");
            const select = document.getElementById(selectId);
            if (!select) return;

            const opcoesOriginais = Array.from(select.options).map((opcao) => ({
                value: opcao.value,
                text: opcao.text,
                selected: opcao.selected,
            }));

            const opcaoPlaceholder = opcoesOriginais.find((opcao) => opcao.value === "");
            const opcoesDados = opcoesOriginais.filter((opcao) => opcao.value !== "");

            function renderizar(term) {
                const termo = (term || "").trim().toLowerCase();
                const valorAtual = select.value;
                const filtradas = !termo
                    ? opcoesDados
                    : opcoesDados.filter((opcao) => opcao.text.toLowerCase().includes(termo));

                select.innerHTML = "";
                const placeholder = document.createElement("option");
                placeholder.value = "";
                placeholder.textContent = opcaoPlaceholder ? opcaoPlaceholder.text : "Selecione";
                select.appendChild(placeholder);

                filtradas.forEach((opcao) => {
                    const node = document.createElement("option");
                    node.value = opcao.value;
                    node.textContent = opcao.text;
                    select.appendChild(node);
                });

                if (filtradas.some((opcao) => opcao.value === valorAtual)) {
                    select.value = valorAtual;
                } else if (!termo && opcoesOriginais.some((opcao) => opcao.selected)) {
                    const selecionadaInicial = opcoesOriginais.find((opcao) => opcao.selected);
                    if (selecionadaInicial && selecionadaInicial.value) {
                        select.value = selecionadaInicial.value;
                    }
                } else {
                    select.value = "";
                }
            }

            campoBusca.addEventListener("input", function () {
                renderizar(campoBusca.value);
            });
        });
    }

    initBuscaAdolescente();

    const form = document.getElementById("novo-cumprimento-form");
    if (!form) return;

    const adolescenteSelect = form.querySelector('select[name="adolescente_id"]');
    const dataInput = document.getElementById("novo-cumprimento-data");
    const aviso = document.getElementById("datas-presenca-bloqueadas");
    const checkboxes = Array.from(form.querySelectorAll('input[name="atividade_ids"]'));
    const presencaId = Number(form.dataset.presencaId || "0");
    const appsId = Number(form.dataset.appsId || "0");
    const mapaDatasPresenca = JSON.parse(form.dataset.datasPresenca || "{}");
    const mapaDatasApps = JSON.parse(form.dataset.datasAppsLancadas || "{}");
    const datasAppsFase = JSON.parse(form.dataset.datasAppsFase || "[]");
    const appsWrapper = document.getElementById("apps-fase-data-wrapper");
    const appsSelect = document.getElementById("apps-fase-data-select");
    const appsStatusWrapper = document.getElementById("apps-status-wrapper");
    const appsCumpriuSelect = document.getElementById("apps-cumpriu-select");
    const appsJustificativaWrapper = document.getElementById("apps-justificativa-wrapper");

    if (!adolescenteSelect || !dataInput || !aviso) return;

    function atividadeSelecionada(atividadeId) {
        if (!atividadeId) return false;
        return checkboxes.some((item) => item.checked && Number(item.value) === atividadeId);
    }

    function datasPresencaDoAdolescente() {
        const id = adolescenteSelect.value || "";
        return mapaDatasPresenca[id] || [];
    }

    function datasAppsDoAdolescente() {
        const id = adolescenteSelect.value || "";
        return mapaDatasApps[id] || [];
    }

    function atualizarAvisoPresenca() {
        if (!atividadeSelecionada(presencaId)) {
            aviso.textContent = "";
            return;
        }

        const datas = datasPresencaDoAdolescente();
        if (!datas.length) {
            aviso.textContent = "";
            return;
        }

        const formatadas = datas
            .map((dataIso) => {
                const [ano, mes, dia] = dataIso.split("-");
                return `${dia}/${mes}/${ano}`;
            })
            .join(", ");

        aviso.textContent = `Datas de presença já lançadas para este adolescente: ${formatadas}.`;
    }

    function controlarDatasApps() {
        if (!appsWrapper || !appsSelect) return;

        const datasUsadas = datasAppsDoAdolescente();
        Array.from(appsSelect.options).forEach((option) => {
            if (!option.value) return;
            option.disabled = datasUsadas.includes(option.value);
        });

        if (!atividadeSelecionada(appsId)) {
            appsWrapper.style.display = "none";
            if (appsStatusWrapper) appsStatusWrapper.style.display = "none";
            if (appsJustificativaWrapper) appsJustificativaWrapper.style.display = "none";
            appsSelect.value = "";
            return;
        }

        appsWrapper.style.display = "grid";
        if (appsStatusWrapper) appsStatusWrapper.style.display = "grid";
        if (appsCumpriuSelect && appsCumpriuSelect.value === "0") {
            if (appsJustificativaWrapper) appsJustificativaWrapper.style.display = "grid";
        } else if (appsJustificativaWrapper) {
            appsJustificativaWrapper.style.display = "none";
        }
        if (datasAppsFase.includes(dataInput.value)) {
            appsSelect.value = dataInput.value;
        } else if (appsSelect.value) {
            dataInput.value = appsSelect.value;
        } else {
            const primeiraDisponivel = Array.from(appsSelect.options).find((option) => option.value && !option.disabled);
            if (primeiraDisponivel) {
                appsSelect.value = primeiraDisponivel.value;
                dataInput.value = primeiraDisponivel.value;
            }
        }
    }

    function validarDataPresenca() {
        if (!atividadeSelecionada(presencaId)) {
            dataInput.setCustomValidity("");
            return;
        }

        const dataSelecionada = dataInput.value;
        const bloqueadas = datasPresencaDoAdolescente();

        if (dataSelecionada && bloqueadas.includes(dataSelecionada)) {
            dataInput.setCustomValidity(
                "A presença nesta data já foi lançada para esse adolescente. Use a opção de editar."
            );
        } else {
            dataInput.setCustomValidity("");
        }
    }

    function validarDataApps() {
        if (!atividadeSelecionada(appsId)) return true;
        const dataSelecionada = dataInput.value;
        if (!datasAppsFase.includes(dataSelecionada)) return false;
        if (datasAppsDoAdolescente().includes(dataSelecionada)) return false;
        return true;
    }

    form.addEventListener("submit", function (event) {
        validarDataPresenca();
        controlarDatasApps();

        if (!validarDataApps()) {
            event.preventDefault();
            dataInput.setCustomValidity("Para lançar APPS, escolha uma das datas da fase 1.");
            form.reportValidity();
            return;
        }

        if (!form.checkValidity()) {
            event.preventDefault();
            form.reportValidity();
        }
    });

    adolescenteSelect.addEventListener("change", function () {
        atualizarAvisoPresenca();
        validarDataPresenca();
    });

    dataInput.addEventListener("change", function () {
        validarDataPresenca();
        if (appsSelect && atividadeSelecionada(appsId) && datasAppsFase.includes(dataInput.value)) {
            appsSelect.value = dataInput.value;
        }
    });

    if (appsSelect) {
        appsSelect.addEventListener("change", function () {
            if (appsSelect.value) {
                dataInput.value = appsSelect.value;
            }
            dataInput.setCustomValidity("");
        });
    }

    if (appsCumpriuSelect) {
        appsCumpriuSelect.addEventListener("change", function () {
            if (!appsJustificativaWrapper) return;
            appsJustificativaWrapper.style.display = appsCumpriuSelect.value === "0" ? "grid" : "none";
        });
    }

    checkboxes.forEach((checkbox) => {
        checkbox.addEventListener("change", function () {
            atualizarAvisoPresenca();
            validarDataPresenca();
            controlarDatasApps();
        });
    });

    atualizarAvisoPresenca();
    controlarDatasApps();
})();
