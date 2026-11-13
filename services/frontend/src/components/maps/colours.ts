// The exits' colours on /maps (the graph's edges and ports, the Links tables): the /flows canvas's,
// kept here so /maps owns its drawing and the Links panel does not pull in React Flow.
export const EXIT_COLOURS: Record<string, string> = {
  walk_exit: "#4c97ff",
  npc_warp: "#b07cff",
  item_warp: "#f5a623",
  death_respawn: "#ff5d5d",
};
