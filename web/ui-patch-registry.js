/* UI patch registry.
 *
 * Several feature files extend the workspace by wrapping a function that is
 * declared with a global `function` declaration in another file, e.g.
 *
 *     writingControls = uiPatchRegistry.wrap('writingControls', writingControls,
 *       'writing-design.js', previous => function () {
 *         previous();
 *         writingDesignUpdate();
 *       });
 *
 * Before this registry that wrap was a plain reassignment, and index.html line
 * order was the only thing making it work. Two failures were silent:
 *
 *   1. If the file declaring the target loaded after the patching file, the
 *      patch ran against undefined and the later declaration overwrote it. The
 *      feature simply vanished, with no error.
 *   2. Two files patching the same target produced an order-dependent chain
 *      that nothing recorded, so any change required reading every script.
 *
 * wrap() keeps the same chaining semantics but makes them explicit: it throws
 * when the target is not a function yet (case 1), and it records which file
 * applied which patch in what order (case 2) for describe().
 *
 * Chaining several patches onto one target is supported and expected;
 * hubNotifyState is patched by both editor-ai.js and hub-design.js.
 */

const uiPatchRegistry = (function () {
  const chains = new Map();

  function wrap(name, target, owner, build) {
    if (typeof owner !== 'string' || !owner) throw new Error('UI patch "' + name + '" needs an owner file name');
    if (typeof name !== 'string' || !name) throw new Error('UI patch in ' + owner + ' needs a target name');
    if (typeof build !== 'function') throw new Error('UI patch "' + name + '" in ' + owner + ' needs a builder function');
    if (typeof target !== 'function') {
      throw new Error('UI patch "' + name + '" in ' + owner + ' found no target function; ' +
        'the file declaring ' + name + ' must load before ' + owner + ' in index.html');
    }
    const chain = chains.get(name) || [];
    if (chain.includes(owner)) {
      throw new Error('UI patch "' + name + '" in ' + owner + ' was applied twice by the same file');
    }
    chain.push(owner);
    chains.set(name, chain);
    return build(target);
  }

  /* Applied patches, in load order: ["hubNotifyState <- editor-ai.js", ...]. */
  function describe() {
    const entries = [];
    for (const [name, owners] of chains) {
      for (const owner of owners) entries.push(name + ' <- ' + owner);
    }
    return entries;
  }

  return { wrap: wrap, describe: describe };
})();
