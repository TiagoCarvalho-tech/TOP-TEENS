(function () {
    const form = document.getElementById("novo-cumprimento-form");
    if (!form) return;

    const adolescenteSelect = form.querySelector('select[name="adolescente_id"]');
    const dataInput = document.getElementById("novo-cumprimento-data");
    const aviso = document.getElementById("datas-presenca-bloqueadas");
    const presencaId = Number(form.dataset.presencaId || "0");
    const mapaDatas = JSON.parse(form.dataset.datasPresenca || "{}");

    if (!adolescenteSelect || !dataInput || !aviso || !presencaId) return;

    function presencaSelecionada() {
        return Array.from(form.querySelectorAll('input[name="atividade_ids"]:checked'))
            .some((item) => Number(item.value) === presencaId);
    }

    function datasBloqueadasDoAdolescente() {
        const id = adolescenteSelect.value || "";
        return mapaDatas[id] || [];
    }

    function atualizarAviso() {
        const datas = datasBloqueadasDoAdolescente();
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

    function validarDataPresenca() {
        if (!presencaSelecionada()) {
            dataInput.setCustomValidity("");
            return;
        }

        const dataSelecionada = dataInput.value;
        const bloqueadas = datasBloqueadasDoAdolescente();

        if (dataSelecionada && bloqueadas.includes(dataSelecionada)) {
            dataInput.setCustomValidity(
                "A presença nesta data já foi lançada para esse adolescente. Use a opção de editar."
            );
        } else {
            dataInput.setCustomValidity("");
        }
    }

    form.addEventListener("submit", function (event) {
        validarDataPresenca();
        if (!form.checkValidity()) {
            event.preventDefault();
            form.reportValidity();
        }
    });

    adolescenteSelect.addEventListener("change", function () {
        atualizarAviso();
        validarDataPresenca();
    });

    dataInput.addEventListener("change", validarDataPresenca);
    form.querySelectorAll('input[name="atividade_ids"]').forEach((checkbox) => {
        checkbox.addEventListener("change", validarDataPresenca);
    });

    atualizarAviso();
})();
