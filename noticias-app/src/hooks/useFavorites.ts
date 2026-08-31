import { useCallback, useEffect, useState } from "react";

import { alternarFavorito, buscarFavoritos } from "../api/news";

/**
 * Favoritos do usuário autenticado.
 *
 * A versão anterior identificava o usuário pelo e-mail vindo do LMS na query
 * string, sem verificação de posse. Agora a identidade é o JWT — o mesmo do
 * app principal —, então o backend sabe de quem é o favorito sem confiar em
 * nada que o navegador informe.
 */
export function useFavorites() {
  const [favoriteIds, setFavoriteIds] = useState<Set<number>>(new Set());
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;

    buscarFavoritos()
      .then((data) => {
        if (!cancelled) setFavoriteIds(new Set(data.article_ids));
      })
      .catch(() => {
        // Falhar aqui não pode quebrar a página: fica sem favoritos marcados.
        if (!cancelled) setFavoriteIds(new Set());
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, []);

  const toggleFavorite = useCallback(
    async (articleId: number) => {
      // Atualização otimista: reflete na UI antes da resposta, revertendo se falhar.
      const eraFavorito = favoriteIds.has(articleId);
      setFavoriteIds((prev) => {
        const next = new Set(prev);
        if (eraFavorito) next.delete(articleId);
        else next.add(articleId);
        return next;
      });

      try {
        const data = await alternarFavorito(articleId);
        setFavoriteIds(new Set(data.article_ids));
      } catch {
        setFavoriteIds((prev) => {
          const next = new Set(prev);
          if (eraFavorito) next.add(articleId);
          else next.delete(articleId);
          return next;
        });
      }
    },
    [favoriteIds]
  );

  return { favoriteIds, loading, toggleFavorite, canFavorite: true };
}
