/**
 * Returns a debounced version of fn that delays invocation until
 * at least waitMs have elapsed since the last call.
 */
export function debounce(fn, waitMs) {
  let timer = null;
  function debounced(...args) {
    clearTimeout(timer);
    timer = setTimeout(() => {
      timer = null;
      fn.apply(this, args);
    }, waitMs);
  }
  debounced.cancel = () => {
    clearTimeout(timer);
    timer = null;
  };
  return debounced;
}

export default debounce;
