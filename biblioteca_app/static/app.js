// Auto-cierra los mensajes flash tras unos segundos
document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('.flash-group .flash').forEach((el) => {
    setTimeout(() => {
      el.style.transition = 'opacity .4s ease';
      el.style.opacity = '0';
      setTimeout(() => el.remove(), 450);
    }, 6000);
  });
});
