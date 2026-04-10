(function () {
    const form = document.querySelector("[data-foto-upload-form]");
    const input = document.querySelector("[data-foto-input]");
    const feedback = document.querySelector("[data-upload-feedback]");
    if (!form || !input || !feedback) return;

    const MAX_UPLOAD_BYTES = 10 * 1024 * 1024;
    const MAX_IMAGE_SIDE = 1024;
    const ALLOWED_EXTENSIONS = new Set(["jpg", "jpeg", "png"]);
    const ALLOWED_TYPES = new Set(["image/jpeg", "image/png"]);
    let processing = false;

    function setFeedback(message, state) {
        feedback.textContent = message || "";
        if (!state) {
            feedback.removeAttribute("data-state");
            return;
        }
        feedback.setAttribute("data-state", state);
    }

    function extensionFromName(fileName) {
        const parts = (fileName || "").toLowerCase().split(".");
        return parts.length > 1 ? parts.pop() : "";
    }

    function formatBytes(value) {
        if (!Number.isFinite(value) || value <= 0) return "0 KB";
        const units = ["B", "KB", "MB"];
        let size = value;
        let index = 0;
        while (size >= 1024 && index < units.length - 1) {
            size /= 1024;
            index += 1;
        }
        return `${size.toFixed(index === 0 ? 0 : 1)} ${units[index]}`;
    }

    function canvasToBlob(canvas, type, quality) {
        return new Promise((resolve, reject) => {
            canvas.toBlob((blob) => {
                if (!blob) {
                    reject(new Error("Falha ao converter imagem."));
                    return;
                }
                resolve(blob);
            }, type, quality);
        });
    }

    function loadImage(file) {
        return new Promise((resolve, reject) => {
            const image = new Image();
            image.onload = function () {
                resolve(image);
            };
            image.onerror = function () {
                reject(new Error("Não foi possível ler a imagem selecionada."));
            };
            image.src = URL.createObjectURL(file);
        });
    }

    async function compressImage(file) {
        const image = await loadImage(file);
        const width = image.naturalWidth || image.width || 0;
        const height = image.naturalHeight || image.height || 0;
        if (!width || !height) {
            URL.revokeObjectURL(image.src);
            throw new Error("Imagem inválida.");
        }

        const ratio = Math.min(1, MAX_IMAGE_SIDE / Math.max(width, height));
        const targetWidth = Math.max(1, Math.round(width * ratio));
        const targetHeight = Math.max(1, Math.round(height * ratio));
        const canvas = document.createElement("canvas");
        canvas.width = targetWidth;
        canvas.height = targetHeight;
        const ctx = canvas.getContext("2d");
        ctx.drawImage(image, 0, 0, targetWidth, targetHeight);
        URL.revokeObjectURL(image.src);

        const ext = extensionFromName(file.name);
        const outputType = ext === "png" ? "image/png" : "image/jpeg";
        let quality = 0.86;
        let blob = await canvasToBlob(canvas, outputType, quality);

        if (outputType === "image/jpeg") {
            while (blob.size > MAX_UPLOAD_BYTES && quality > 0.55) {
                quality = Math.max(0.55, quality - 0.06);
                blob = await canvasToBlob(canvas, outputType, quality);
            }
        }

        const baseName = (file.name || "foto").replace(/\.[^.]+$/, "");
        const finalExt = outputType === "image/png" ? "png" : "jpg";
        const finalName = `${baseName}.${finalExt}`.replace(/\s+/g, "_");
        return new File([blob], finalName, {
            type: outputType,
            lastModified: Date.now(),
        });
    }

    function validateType(file) {
        const ext = extensionFromName(file.name);
        if (!ALLOWED_EXTENSIONS.has(ext)) return false;
        if (!file.type) return true;
        return ALLOWED_TYPES.has(file.type);
    }

    function toggleSubmit(disabled) {
        const button = form.querySelector('button[type="submit"]');
        if (button) button.disabled = disabled;
    }

    input.addEventListener("change", async function () {
        const file = input.files && input.files[0];
        setFeedback("", null);
        if (!file) return;

        if (!validateType(file)) {
            input.value = "";
            setFeedback("Formato inválido. Envie JPG, JPEG ou PNG.", "error");
            return;
        }

        processing = true;
        toggleSubmit(true);
        setFeedback("Otimizando imagem para envio...", null);

        try {
            const compressed = await compressImage(file);
            if (compressed.size > MAX_UPLOAD_BYTES) {
                input.value = "";
                setFeedback("A imagem final ainda ficou maior que 10MB. Use uma foto menor.", "error");
                return;
            }

            if (typeof DataTransfer === "undefined") {
                if (file.size > MAX_UPLOAD_BYTES) {
                    input.value = "";
                    setFeedback("Seu navegador não suporta otimização automática. Envie uma imagem menor que 10MB.", "error");
                    return;
                }
                setFeedback("Imagem pronta para envio.", "ok");
                return;
            }

            const transfer = new DataTransfer();
            transfer.items.add(compressed);
            input.files = transfer.files;
            setFeedback(
                `Imagem pronta: ${formatBytes(file.size)} → ${formatBytes(compressed.size)} (${Math.round(compressed.size * 100 / file.size)}%).`,
                "ok",
            );
        } catch (_error) {
            input.value = "";
            setFeedback("Não foi possível processar a foto. Escolha outra imagem.", "error");
        } finally {
            processing = false;
            toggleSubmit(false);
        }
    });

    form.addEventListener("submit", function (event) {
        if (processing) {
            event.preventDefault();
            setFeedback("Aguarde a otimização da imagem terminar.", "error");
            return;
        }

        const file = input.files && input.files[0];
        if (!file) return;

        if (!validateType(file)) {
            event.preventDefault();
            setFeedback("Formato inválido. Envie JPG, JPEG ou PNG.", "error");
            return;
        }

        if (file.size > MAX_UPLOAD_BYTES) {
            event.preventDefault();
            setFeedback("Arquivo muito grande. O limite é 10MB.", "error");
        }
    });
})();
