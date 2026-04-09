BEGIN;

-- 1) Garante atividades base usadas no cálculo da Fase 1.
INSERT INTO atividades (nome, pontos, descricao, ativo)
SELECT 'Presença', 10, 'Presença da semana', 1
WHERE NOT EXISTS (
    SELECT 1 FROM atividades WHERE lower(trim(nome)) IN ('presença', 'presenca', 'presença culto')
);

INSERT INTO atividades (nome, pontos, descricao, ativo)
SELECT 'Meditação e Versículo', 20, 'Meditação + versículo', 1
WHERE NOT EXISTS (
    SELECT 1 FROM atividades WHERE lower(trim(nome)) IN ('meditação e versículo', 'meditacao e versiculo', 'meditação e versiculo', 'meditação')
);

INSERT INTO atividades (nome, pontos, descricao, ativo)
SELECT 'Anotação e Bíblia', 10, 'Leitura com anotação', 1
WHERE NOT EXISTS (
    SELECT 1 FROM atividades WHERE lower(trim(nome)) IN ('anotação e bíblia', 'anotacao e biblia', 'bíblia e anotação', 'biblia e anotacao')
);

DO $$
DECLARE
    v_target_id INTEGER;
    v_lider_id INTEGER;
    v_p INTEGER;
    v_mv INTEGER;
    v_ab INTEGER;
    v_data TEXT;
BEGIN
    -- 2) Localiza um líder com GA Lírios para vincular o cadastro alvo.
    SELECT id
    INTO v_lider_id
    FROM usuarios
    WHERE lower(trim(COALESCE(lider_ga, ''))) = lower('GA Lírios')
    ORDER BY id
    LIMIT 1;

    -- 3) Mantém apenas a adolescente solicitada; cria se não existir.
    SELECT id
    INTO v_target_id
    FROM adolescentes
    WHERE lower(trim(nome)) = lower('Diva Emanuele Brandão Vinhote')
    ORDER BY id
    LIMIT 1;

    IF v_target_id IS NULL THEN
        INSERT INTO adolescentes (
            lider_id, matricula, foto_path, nome, nascimento, contato, sexo, pai, mae, lider_ga
        )
        VALUES (
            v_lider_id,
            'DIVA' || to_char(clock_timestamp(), 'YYYYMMDDHH24MISSMS'),
            NULL,
            'Diva Emanuele Brandão Vinhote',
            '2011-01-01',
            '',
            'F',
            '',
            '',
            'GA Lírios'
        )
        RETURNING id INTO v_target_id;
    END IF;

    UPDATE adolescentes
    SET
        nome = 'Diva Emanuele Brandão Vinhote',
        lider_ga = 'GA Lírios',
        lider_id = v_lider_id,
        sexo = 'F',
        nascimento = COALESCE(NULLIF(nascimento, ''), '2011-01-01')
    WHERE id = v_target_id;

    -- Remove todos os outros adolescentes (cascata remove cumprimentos deles).
    DELETE FROM adolescentes
    WHERE id <> v_target_id;

    -- 4) Regrava pontuação da Diva para totalizar 160 pontos (2 cupons).
    SELECT id
    INTO v_p
    FROM atividades
    WHERE lower(trim(nome)) IN ('presença', 'presenca', 'presença culto')
    ORDER BY id
    LIMIT 1;

    SELECT id
    INTO v_mv
    FROM atividades
    WHERE lower(trim(nome)) IN ('meditação e versículo', 'meditacao e versiculo', 'meditação e versiculo', 'meditação')
    ORDER BY id
    LIMIT 1;

    SELECT id
    INTO v_ab
    FROM atividades
    WHERE lower(trim(nome)) IN ('anotação e bíblia', 'anotacao e biblia', 'bíblia e anotação', 'biblia e anotacao')
    ORDER BY id
    LIMIT 1;

    DELETE FROM cumprimentos_tarefas
    WHERE adolescente_id = v_target_id;

    FOREACH v_data IN ARRAY ARRAY['2026-03-15', '2026-03-22', '2026-03-29', '2026-04-12']
    LOOP
        INSERT INTO cumprimentos_tarefas (
            adolescente_id, atividade_id, data_cumprimento, cumpriu, observacoes, falta_justificada
        ) VALUES
            (v_target_id, v_p, v_data, 1, '', 0),
            (v_target_id, v_mv, v_data, 1, '', 0),
            (v_target_id, v_ab, v_data, 1, '', 0);
    END LOOP;
END $$;

COMMIT;

-- Validação rápida esperada:
-- 1 adolescente, total 160 pts, 2 cupons.
-- SELECT id, nome, lider_ga FROM adolescentes;
-- SELECT adolescente_id, COUNT(*) FROM cumprimentos_tarefas GROUP BY adolescente_id;
