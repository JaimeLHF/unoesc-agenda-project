import React from 'react';

/**
 * Ícones da interface, em SVG de traço.
 *
 * Substituem os emojis que a interface usava antes. Emoji é desenhado pelo
 * sistema operacional: o mesmo 🔔 aparece azul no Windows, cinza no Android e
 * amarelo no iPhone, em tamanhos diferentes, e nenhum deles combina com a
 * paleta do app. Estes herdam `currentColor` e o tamanho do texto ao redor,
 * então acompanham a cor de cada contexto — inclusive no hover de um botão.
 *
 * Traço de 1.75 com pontas arredondadas, todos no mesmo grid de 24×24: é o que
 * faz um conjunto de ícones parecer um conjunto, e não uma coleção.
 */

export type IconName =
  | 'marca'
  | 'atualizar'
  | 'organizar'
  | 'alerta'
  | 'urgente'
  | 'relogio'
  | 'calendario'
  | 'sino'
  | 'video'
  | 'entrega'
  | 'prova'
  | 'pin'
  | 'check'
  | 'voltar'
  | 'link-externo'
  | 'desfazer'
  | 'menu'
  | 'limpar'
  | 'sair'
  | 'lixeira'
  | 'fechar'
  | 'perfil'
  | 'sol'
  | 'lua'
  | 'sem-conexao';

/**
 * Só o miolo de cada ícone. O `<svg>` em volta é montado uma vez no componente,
 * o que garante o mesmo viewBox e a mesma espessura de traço em todos.
 */
const PATHS: Record<IconName, React.ReactNode> = {
  // Marca: um calendário com um traço de conferido dentro — agenda + feito.
  marca: (
    <>
      <rect x="3" y="4.5" width="18" height="16" rx="3" />
      <path d="M8 2.5v4M16 2.5v4M3 9.5h18" />
      <path d="m8.5 14.5 2.5 2.5 4.5-4.5" />
    </>
  ),
  atualizar: (
    <>
      <path d="M21 12a9 9 0 1 1-2.64-6.36" />
      <path d="M21 3v5h-5" />
    </>
  ),
  organizar: (
    <>
      <path d="M12 3v4M12 17v4M3 12h4M17 12h4" />
      <path d="M9.5 9.5 6.8 6.8M14.5 9.5l2.7-2.7M9.5 14.5l-2.7 2.7M14.5 14.5l2.7 2.7" />
      <circle cx="12" cy="12" r="2.5" />
    </>
  ),
  alerta: (
    <>
      <path d="M10.3 3.9 1.9 18a2 2 0 0 0 1.7 3h16.8a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0Z" />
      <path d="M12 9v4M12 17h.01" />
    </>
  ),
  urgente: (
    <>
      <circle cx="12" cy="12" r="9" />
      <path d="M12 7v5M12 16h.01" />
    </>
  ),
  relogio: (
    <>
      <circle cx="12" cy="12" r="9" />
      <path d="M12 7v5l3.5 2" />
    </>
  ),
  calendario: (
    <>
      <rect x="3" y="4.5" width="18" height="16" rx="3" />
      <path d="M8 2.5v4M16 2.5v4M3 9.5h18" />
    </>
  ),
  sino: (
    <>
      <path d="M18 8.5a6 6 0 1 0-12 0c0 6-2 7.5-2 7.5h16s-2-1.5-2-7.5Z" />
      <path d="M10.3 20a2 2 0 0 0 3.4 0" />
    </>
  ),
  video: (
    <>
      <rect x="2.5" y="6" width="13" height="12" rx="2.5" />
      <path d="m15.5 10.5 6-3.5v10l-6-3.5Z" />
    </>
  ),
  entrega: (
    <>
      <path d="M12 16V4M12 4 7.5 8.5M12 4l4.5 4.5" />
      <path d="M4 15v3.5a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V15" />
    </>
  ),
  prova: (
    <>
      <path d="M15 2.5H7a2 2 0 0 0-2 2v15a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V6.5Z" />
      <path d="M14.5 2.5V7h4.5M8.5 12h7M8.5 16h4" />
    </>
  ),
  pin: (
    <>
      <path d="M12 21v-7" />
      <path d="M9 3h6l-1 5 3 3v2H7v-2l3-3-1-5Z" />
    </>
  ),
  check: <path d="m4.5 12.5 5 5 10-11" />,
  voltar: (
    <>
      <path d="M19 12H5" />
      <path d="m11 6-6 6 6 6" />
    </>
  ),
  'link-externo': (
    <>
      <path d="M14 4h6v6" />
      <path d="M20 4 10.5 13.5" />
      <path d="M19 14.5V19a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2h4.5" />
    </>
  ),
  desfazer: (
    <>
      <path d="M3 12a9 9 0 1 0 2.64-6.36" />
      <path d="M3 3v5h5" />
    </>
  ),
  menu: (
    <>
      <circle cx="12" cy="5" r="1.4" />
      <circle cx="12" cy="12" r="1.4" />
      <circle cx="12" cy="19" r="1.4" />
    </>
  ),
  // Dados salvos (cilindro de banco) com um corte: apaga o cache, não a conta.
  // Precisa ser diferente do ícone de atualizar, que também é circular — dois
  // itens do mesmo menu com a mesma seta seriam lidos como a mesma ação.
  limpar: (
    <>
      <ellipse cx="12" cy="6" rx="7.5" ry="3" />
      <path d="M4.5 6v6c0 1.7 3.4 3 7.5 3s7.5-1.3 7.5-3V6" />
      <path d="M4.5 12v6c0 1.7 3.4 3 7.5 3" />
      <path d="m15 21 6-6" />
    </>
  ),
  sair: (
    <>
      <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
      <path d="M16 17l5-5-5-5M21 12H9" />
    </>
  ),
  lixeira: (
    <>
      <path d="M3.5 6.5h17M9 6.5V4.5a1.5 1.5 0 0 1 1.5-1.5h3A1.5 1.5 0 0 1 15 4.5v2" />
      <path d="M6.5 6.5 7.4 20a1.5 1.5 0 0 0 1.5 1.4h6.2a1.5 1.5 0 0 0 1.5-1.4l.9-13.5" />
      <path d="M10.5 11v6M13.5 11v6" />
    </>
  ),
  fechar: <path d="M6 6l12 12M18 6 6 18" />,
  perfil: (
    <>
      <circle cx="12" cy="8" r="3.75" />
      <path d="M4.5 20.5a7.5 7.5 0 0 1 15 0" />
    </>
  ),
  sol: (
    <>
      <circle cx="12" cy="12" r="4" />
      <path d="M12 2.5v2M12 19.5v2M2.5 12h2M19.5 12h2M5.2 5.2l1.4 1.4M17.4 17.4l1.4 1.4M18.8 5.2l-1.4 1.4M6.6 17.4l-1.4 1.4" />
    </>
  ),
  lua: <path d="M20 13.5A8.5 8.5 0 0 1 10.5 4a8.5 8.5 0 1 0 9.5 9.5Z" />,
  'sem-conexao': (
    <>
      <path d="M3 3l18 18" />
      <path d="M8.5 15.5a5 5 0 0 1 7 0" />
      <path d="M5 12a10 10 0 0 1 3.5-2.3M19 12a10 10 0 0 0-7.8-2.9" />
      <path d="M12 20h.01" />
    </>
  ),
};

interface IconProps {
  name: IconName;
  /** Em `em`, para o ícone crescer junto com o texto do contexto. */
  size?: number;
  className?: string;
  /**
   * Só quando o ícone é a única coisa dentro do botão. Com texto ao lado, ele é
   * decorativo e fica escondido do leitor de tela — que já lê o texto.
   */
  label?: string;
}

const Icon: React.FC<IconProps> = ({ name, size = 1.15, className, label }) => (
  <svg
    className={className ? `icon ${className}` : 'icon'}
    viewBox="0 0 24 24"
    width={`${size}em`}
    height={`${size}em`}
    fill="none"
    stroke="currentColor"
    strokeWidth={1.75}
    strokeLinecap="round"
    strokeLinejoin="round"
    role={label ? 'img' : undefined}
    aria-label={label}
    aria-hidden={label ? undefined : true}
    focusable="false"
  >
    {PATHS[name]}
  </svg>
);

export default Icon;
