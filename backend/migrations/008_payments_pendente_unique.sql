-- M6.3: impede duas cobrancas pendentes simultaneas para o mesmo (user, plano).
-- O check "pendente vigente -> skip" no codigo tem corrida: dois workers
-- veem vazio antes de qualquer INSERT. O indice fecha a corrida no banco.
CREATE UNIQUE INDEX payments_pendente_uq
  ON payments (user_id, plano)
  WHERE status = 'pendente';
