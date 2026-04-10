(function () {
    const form = document.querySelector("[data-foto-upload-form]");
    const input = document.querySelector("[data-foto-input]");
    const feedback = document.querySelector("[data-upload-feedback]");
    const previewBox = document.querySelector("[data-upload-preview]");
    const previewImage = document.querySelector("[data-upload-preview-image]");
    const previewPlaceholder = document.querySelector("[data-upload-preview-placeholder]");
    if (!form || !input || !feedback) return;

    const maxUploadMb = Math.max(1, Number(form.dataset.maxUploadMb || 10));
    const MAX_UPLOAD_BYTES = maxUploadMb * 1024 * 1024;
    const MAX_IMAGE_SIDE = 1024;
    const ALLOWED_EXTENSIONS = new Set(["jpg", "jpeg", "png"]);
    const ALLOWED_TYPES = new Set(["image/jpeg", "image/jpg", "image/pjpeg", "image/png", "image/x-png"]);
    let processing = false;
    let previewUrl = "";

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

    function clearPreview() {
        if (!previewBox || !previewImage || !previewPlaceholder) return;
        if (previewUrl) {
            URL.revokeObjectURL(previewUrl);
            previewUrl = "";
        }
        previewImage.src = "";
        previewImage.hidden = true;
        previewPlaceholder.hidden = false;
    }

    function showPreview(file) {
        if (!previewBox || !previewImage || !previewPlaceholder || !file) return;
        if (previewUrl) URL.revokeObjectURL(previewUrl);
        previewUrl = URL.createObjectURL(file);
        previewImage.src = previewUrl;
        previewImage.hidden = false;
        previewPlaceholder.hidden = true;
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
                reject(new Error("READ_ERROR"));
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
            throw new Error("INVALID_DIMENSIONS");
        }

        const ratio = Math.min(1, MAX_IMAGE_SIDE / Math.max(width, height));
        const targetWidth = Math.max(1, Math.round(width * ratio));
        const targetHeight = Math.max(1, Math.round(height * ratio));
        const canvas = document.createElement("canvas");
        canvas.width = targetWidth;
        canvas.height = targetHeight;
        const ctx = canvas.getContext("2d");
        if (!ctx) {
            URL.revokeObjectURL(image.src);
            throw new Error("CANVAS_CONTEXT_ERROR");
        }
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

    function validarTipo(file) {
        const ext = extensionFromName(file.name);
        if (!ALLOWED_EXTENSIONS.has(ext)) return false;
        if (!file.type) return true;
        return ALLOWED_TYPES.has(file.type);
    }

    function mensagemErroProcessamento(codigo) {
        const mensagens = {
            READ_ERROR: "Não foi possível ler essa imagem no navegador.",
            INVALID_DIMENSIONS: "Imagem inválida ou sem dimensões válidas.",
            CANVAS_CONTEXT_ERROR: "Seu navegador não conseguiu iniciar a otimização da imagem.",
        };
        return mensagens[codigo] || "Não foi possível processar a foto automaticamente.";
    }

    function toggleSubmit(disabled) {
        const button = form.querySelector('button[type="submit"]');
        if (button) button.disabled = disabled;
    }

    input.addEventListener("change", async function () {
        const file = input.files && input.files[0];
        setFeedback("", null);
        if (!file) {
            clearPreview();
            return;
        }

        if (!validarTipo(file)) {
            input.value = "";
            setFeedback("Formato inválido. Envie JPG, JPEG ou PNG.", "error");
            clearPreview();
            return;
        }

        processing = true;
        toggleSubmit(true);
        setFeedback("Otimizando imagem para envio...", null);

        try {
            const compressed = await compressImage(file);
            if (compressed.size > MAX_UPLOAD_BYTES) {
                input.value = "";
                setFeedback(`A imagem final ainda ficou maior que ${maxUploadMb}MB. Use uma foto menor.`, "error");
                clearPreview();
                return;
            }

            if (typeof DataTransfer === "undefined") {
                if (compressed.size > MAX_UPLOAD_BYTES) {
                    input.value = "";
                    setFeedback(`Seu navegador não suporta troca automática do arquivo. Envie uma imagem menor que ${maxUploadMb}MB.`, "error");
                    clearPreview();
                    return;
                }
                showPreview(file);
                setFeedback("Pré-visualização pronta. A imagem será enviada sem otimização automática neste navegador.", "ok");
                return;
            }

            try {
                const transfer = new DataTransfer();
                transfer.items.add(compressed);
                input.files = transfer.files;
            } catch (_swapError) {
                if (file.size > MAX_UPLOAD_BYTES) {
                    input.value = "";
                    setFeedback(`Não foi possível otimizar neste navegador e o arquivo original ultrapassa ${maxUploadMb}MB.`, "error");
                    clearPreview();
                    return;
                }
                showPreview(file);
                setFeedback("Prévia pronta. O navegador não permitiu substituir o arquivo otimizado, então será enviado o original.", "ok");
                return;
            }

            showPreview(compressed);
            setFeedback(
                `Imagem pronta: ${formatBytes(file.size)} -> ${formatBytes(compressed.size)} (${Math.round((compressed.size * 100) / Math.max(file.size, 1))}%).`,
                "ok",
            );
        } catch (error) {
            if (file.size <= MAX_UPLOAD_BYTES) {
                showPreview(file);
                setFeedback(`${mensagemErroProcessamento(error.message)} O arquivo original será enviado.`, "ok");
            } else {
                input.value = "";
                setFeedback(`${mensagemErroProcessamento(error.message)} Escolha outra imagem menor.`, "error");
                clearPreview();
            }
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

        if (!validarTipo(file)) {
            event.preventDefault();
            setFeedback("Formato inválido. Envie JPG, JPEG ou PNG.", "error");
            return;
        }

        if (file.size > MAX_UPLOAD_BYTES) {
            event.preventDefault();
            setFeedback(`Arquivo muito grande. O limite é ${maxUploadMb}MB.`, "error");
        }
    });

    window.addEventListener("beforeunload", clearPreview);
})();
