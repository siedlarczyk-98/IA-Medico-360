/**
 * Perfil do médico: carregar, salvar e excluir a conta.
 *
 * O `ProfileModal` do desktop e a sheet "Editar perfil" da casca mobile
 * desenham campos diferentes com as mesmas regras: e-mail somente leitura,
 * especialidade editável só quando o SERVIDOR diz que é, token renovado ao
 * salvar. Uma cópia dessas regras em cada casca divergiria.
 */

import { useEffect, useState } from 'react';

import { deleteAccount, getMe, listarEspecialidades, updateProfile, type Especialidade } from '../api/auth';
import { logout, setToken } from '../lib/auth';

// De onde veio a especialidade, em português, para explicar por que o campo
// está travado. Sem esta frase o médico vê um texto cinza e não sabe se é bug.
export const ORIGEM_LEGIVEL: Record<string, string> = {
  cadastro: 'Veio do seu cadastro.',
  waid_grupo: 'Veio do seu cadastro.',
  cfm: 'Verificada no Conselho Federal de Medicina.',
  admin: 'Ajustada pelo suporte.',
};

export function usePerfil({ onSuccess, onClose }: { onSuccess: () => void; onClose: () => void }) {
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [crmLabel, setCrmLabel] = useState('');
  const [especialidade, setEspecialidade] = useState('');
  // O rótulo vem pronto do servidor; sem ele, o campo travado mostraria o slug
  // ("ortopedia-e-traumatologia") porque a lista só é buscada quando editável.
  const [especialidadeNome, setEspecialidadeNome] = useState('');
  const [origemEspecialidade, setOrigemEspecialidade] = useState<string | null>(null);
  const [especialidadeEditavel, setEspecialidadeEditavel] = useState(false);
  const [especialidades, setEspecialidades] = useState<Especialidade[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [deleting, setDeleting] = useState(false);

  useEffect(() => {
    getMe()
      .then(user => {
        setName(user.name ?? '');
        setEmail(user.email);
        setCrmLabel(user.crm && user.crm_state ? `CRM/${user.crm_state} ${user.crm}` : '');
        setEspecialidade(user.specialty_slug ?? '');
        setEspecialidadeNome(user.specialty ?? '');
        setOrigemEspecialidade(user.specialty_source ?? null);
        // O servidor decide se o campo é editável — a regra mora em
        // `identidade.usuario_pode_editar`, não aqui. A tela só obedece.
        const editavel = user.specialty_editavel ?? true;
        setEspecialidadeEditavel(editavel);
        if (editavel) {
          listarEspecialidades().then(setEspecialidades).catch(() => setEspecialidades([]));
        }
      })
      .catch(() => setError('Não foi possível carregar os dados do perfil.'))
      .finally(() => setLoading(false));
  }, []);

  async function salvar() {
    setSaving(true);
    setError(null);
    try {
      const res = await updateProfile({
        name: name.trim(),
        ...(especialidadeEditavel && especialidade ? { specialty_slug: especialidade } : {}),
      });
      setToken(res.access_token);
      onSuccess();
      onClose();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Erro ao salvar');
    } finally {
      setSaving(false);
    }
  }

  async function excluirConta(confirmName: string) {
    setDeleting(true);
    setError(null);
    try {
      await deleteAccount(confirmName);
      logout();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Erro ao excluir conta');
      setDeleting(false);
    }
  }

  return {
    name, setName,
    email,
    crmLabel,
    especialidade, setEspecialidade,
    especialidadeNome,
    origemEspecialidade,
    especialidadeEditavel,
    especialidades,
    loading, saving, error, deleting,
    salvar,
    excluirConta,
  };
}
