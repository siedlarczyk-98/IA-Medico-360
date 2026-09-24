import { useQuery } from '@tanstack/react-query';
import { ErroHttp, getCalculator } from '../api/calculators';

export function useCalculatorDetail(slug: string) {
  return useQuery({
    queryKey: ['calculator', slug],
    queryFn: () => getCalculator(slug),
    staleTime: 10 * 60 * 1000,
    // Repetir só o que pode mudar sozinho (rede, 5xx). 404 não vai aparecer, e
    // o 401 já disparou a reentrada — repetir só atrasaria a tela certa.
    retry: (tentativas, erro) =>
      !(erro instanceof ErroHttp && erro.status < 500) && tentativas < 1,
  });
}
