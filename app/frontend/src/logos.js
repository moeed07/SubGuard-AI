import chatgptLogo from './assets/logos/chatgpt.png';
import googleProLogo from './assets/logos/google-ai-pro.png';
import microsoftLogo from './assets/logos/microsoft.png';
import netflixLogo from './assets/logos/netflix.png';
import spotifyLogo from './assets/logos/spotify.png';
import tamashaLogo from './assets/logos/tamasha.webp';
import { subscriptionLogoId } from './portfolio.js';

const LOGOS = {
  chatgpt: chatgptLogo,
  'google-ai-pro': googleProLogo,
  microsoft: microsoftLogo,
  netflix: netflixLogo,
  spotify: spotifyLogo,
  tamasha: tamashaLogo,
};

export function logoForSubscription(subscriptionKey) {
  const id = subscriptionLogoId(subscriptionKey);
  return id ? LOGOS[id] || null : null;
}
