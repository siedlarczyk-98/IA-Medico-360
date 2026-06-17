import { useEffect } from 'react';
import { updateIntercomUser } from './intercom';
import { useCurrentUser } from './useCurrentUser';

/**
 * Associa email + nome do médico logado ao Messenger (já carregado via snippet
 * em main.tsx). Nenhum dado clínico é enviado.
 */
export function IntercomIdentity() {
  const user = useCurrentUser();

  useEffect(() => {
    // Messenger Security enforced: só identifica com user_id + user_hash válidos.
    if (user?.id && user.intercomUserHash) {
      updateIntercomUser({
        user_id: user.id,
        user_hash: user.intercomUserHash,
        email: user.email,
        name: user.name ?? undefined,
      });
    }
  }, [user?.id, user?.intercomUserHash, user?.email, user?.name]);

  return null;
}
