"""Skin-weight tools in plain numpy (no bpy), shared by the character builds.

The builds hand over the rest mesh (vertex positions and triangles), the bones (head, tail, deform flag) and, for every
clip, each bone's deform matrix on every frame (posed bone matrix times the inverse rest matrix, as the Armature
modifier and glTF skinning both use). From these:

  Skin.weld          vertices at one position (the glTF importer splits them along UV seams) share one weight, so a
                     seam can never open
  Skin.smooth        Laplacian smoothing of weights over the mesh, some vertices locked
  Skin.relax         the stretch fix: play every clip with linear blend skinning, find each triangle edge that grows or
                     shrinks past a target (posed length over rest length, or its inverse), and smooth the weights
                     around it; repeat until no edge passes the target
  Skin.measure       the same measure as the build's stretch gate and the node check
  limit              keep the strongest k influences per vertex
  fan_split          cut a mesh between face groups that must not share an edge (vertices doubled, no face changed)
  harmonic           weights fixed at anchor points and harmonic in between (edge weights 1 / length)
  Humanoid           the warriors' weights: cut, anchor, harmonic, relax, searched until the clips pass the gate
"""
import numpy as np


def seg_dist(P, A, B):
    """Distance of each point in P (N, 3) to each segment A[k]-B[k] (K, 3): (N, K)."""
    ab = B - A
    L = np.maximum((ab * ab).sum(1), 1e-12)
    t = np.clip(((P[:, None, :] - A[None]) * ab[None]).sum(2) / L[None], 0.0, 1.0)
    Q = A[None] + t[..., None] * ab[None]
    return np.linalg.norm(Q - P[:, None, :], axis=2)


def limit(W, k=4):
    """Keep the k largest weights per row, normalised."""
    W = W.copy()
    if W.shape[1] > k:
        idx = np.argsort(-W, axis=1)[:, k:]
        np.put_along_axis(W, idx, 0.0, axis=1)
    W[W < 1e-4] = 0.0
    s = W.sum(1, keepdims=True)
    return W / np.maximum(s, 1e-12)


def components(n, edges):
    par = np.arange(n)

    def find(a):
        r = a
        while par[r] != r:
            r = par[r]
        while par[a] != r:
            par[a], a = r, par[a]
        return r

    for a, b in edges:
        ra, rb = find(a), find(b)
        if ra != rb:
            par[rb] = ra
    return np.array([find(i) for i in range(n)])


class Skin:
    def __init__(self, verts, tris, deform, labels=None, tol=1e-5, min_len=1e-3):
        """verts (N, 3) and tris (T, 3) of the rest mesh; deform: bool per bone (weights only go to deform bones);
        labels: an int per vertex, vertices with different labels are never welded (a cut made on purpose)."""
        self.verts = np.asarray(verts, dtype=np.float64)
        key = np.round(self.verts / tol).astype(np.int64)
        if labels is not None:
            key = np.column_stack([key, np.asarray(labels)])
        _, self.wid = np.unique(key, axis=0, return_inverse=True)
        self.wid = self.wid.ravel()
        self.n = int(self.wid.max()) + 1
        cnt = np.bincount(self.wid, minlength=self.n).astype(np.float64)
        self.P = np.zeros((self.n, 3))
        np.add.at(self.P, self.wid, self.verts)
        self.P /= cnt[:, None]
        t = self.wid[np.asarray(tris)]
        e = np.concatenate([t[:, [0, 1]], t[:, [1, 2]], t[:, [2, 0]]])
        e = e[e[:, 0] != e[:, 1]]
        e.sort(axis=1)
        self.E = np.unique(e, axis=0)
        self.L0 = np.linalg.norm(self.P[self.E[:, 0]] - self.P[self.E[:, 1]], axis=1)
        self.meas = self.L0 >= min_len
        self.deform = np.asarray(deform, dtype=bool)
        self.B = len(self.deform)
        self.deg = np.bincount(self.E.ravel(), minlength=self.n).astype(np.float64)
        self.comp = components(self.n, self.E)
        self.clips = {}

    # ---- conversions between split vertices and welded points
    def to_welded(self, Wv):
        W = np.zeros((self.n, Wv.shape[1]))
        np.add.at(W, self.wid, Wv)
        cnt = np.bincount(self.wid, minlength=self.n)[:, None]
        return W / np.maximum(cnt, 1)

    def to_verts(self, W):
        return W[self.wid]

    def islands(self):
        """Loose parts as arrays of welded ids, largest first."""
        out = {}
        for i, c in enumerate(self.comp):
            out.setdefault(c, []).append(i)
        return sorted((np.array(v) for v in out.values()), key=len, reverse=True)

    # ---- weights
    def normalise(self, W):
        W = np.where(self.deform[None], np.maximum(W, 0.0), 0.0)
        s = W.sum(1, keepdims=True)
        bad = s[:, 0] <= 1e-9
        if bad.any():
            raise RuntimeError(f"{bad.sum()} points have no weight")
        return W / s

    def neighbour_mean(self, W):
        acc = np.zeros_like(W)
        np.add.at(acc, self.E[:, 0], W[self.E[:, 1]])
        np.add.at(acc, self.E[:, 1], W[self.E[:, 0]])
        return acc / np.maximum(self.deg, 1)[:, None]

    def smooth(self, W, iters=1, lam=0.5, mask=None, locked=None):
        """Laplacian smoothing of the weights of the points in mask (all by default), never of locked points."""
        upd = np.ones(self.n, bool) if mask is None else mask.copy()
        upd &= self.deg > 0
        if locked is not None:
            upd &= ~locked
        for _ in range(iters):
            M = self.neighbour_mean(W)
            W = np.where(upd[:, None], (1 - lam) * W + lam * M, W)
        return W

    def grow(self, mask, rings=1):
        m = mask.copy()
        for _ in range(rings):
            hit = m[self.E[:, 0]] | m[self.E[:, 1]]
            m[self.E[hit].ravel()] = True
        return m

    # ---- clips and the measure
    def add_clip(self, name, M, step=1):
        """M: (frames, bones, 4, 4) deform matrices; every `step`-th frame and the last are used."""
        M = np.asarray(M, dtype=np.float64)
        idx = sorted(set(range(0, len(M), step)) | {len(M) - 1})
        self.clips[name] = M[idx]

    def pose(self, W, M):
        """Linear blend skinning of the welded points for every frame of M: (F, n, 3)."""
        F = len(M)
        A = M[:, :, :3, :].transpose(1, 0, 2, 3).reshape(self.B, F * 12)
        blend = (W @ A).reshape(self.n, F, 3, 4)
        h = np.concatenate([self.P, np.ones((self.n, 1))], axis=1)
        return np.einsum("nfij,nj->fni", blend, h)

    def edge_q(self, W, clips=None):
        """Worst stretch of each edge over all frames of the given clips, and per clip (worst, frame, >1.5, >2)."""
        q = np.ones(len(self.E))
        per = {}
        for name in clips or self.clips:
            Pf = self.pose(W, self.clips[name])
            L = np.linalg.norm(Pf[:, self.E[:, 0]] - Pf[:, self.E[:, 1]], axis=2) / np.maximum(self.L0, 1e-12)[None]
            Q = np.maximum(L, 1.0 / np.maximum(L, 1e-6))
            Q[:, ~self.meas] = 1.0
            qe = Q.max(0)
            f = int(np.unravel_index(np.argmax(Q), Q.shape)[0])
            per[name] = (round(float(qe.max()), 2), f, int((qe > 1.5).sum()), int((qe > 2.0).sum()))
            q = np.maximum(q, qe)
        return q, per

    def measure(self, W):
        return self.edge_q(W)[1]

    def relax(self, W, target=1.8, locked=None, iters=400, lam=0.5, rings=1, k=4, log=None):
        """Smooth the weights around every edge that the clips stretch or squash past target, until none does.
        Returns the best weights seen (lowest worst edge), so it never makes things worse."""
        best = (np.inf, W)
        for it in range(iters):
            q, per = self.edge_q(W)
            if q.max() < best[0]:
                best = (q.max(), W)
            bad = q > target
            if log and (it % 25 == 0):
                log(f"relax {it}: worst {q.max():.2f}, edges over target {int(bad.sum())}")
            if not bad.any():
                break
            mask = np.zeros(self.n, bool)
            mask[self.E[bad].ravel()] = True
            mask = self.grow(mask, rings)
            W = self.smooth(W, 1, lam, mask, locked)
            W = limit(W, k)
        W = best[1]
        q, per = self.edge_q(W)
        return W, per, it

# ---------------------------------------------------------------- cuts and harmonic weights
def weld_ids(verts, tol=1e-5):
    """One id per position: the glTF importer splits vertices along UV seams; these ids join them again."""
    key = np.round(np.asarray(verts, np.float64) / tol).astype(np.int64)
    _, wid = np.unique(key, axis=0, return_inverse=True)
    return wid.ravel()


def fan_split(tris_w, fgroup, pairs):
    """Cut a mesh between face groups that must not share an edge (`pairs`: a set of frozenset({a, b})).
    tris_w: triangles in welded ids. An edge is cut when its two triangles' groups are a pair. Around each point the
    triangles are clustered by the uncut edges they share there; each cluster becomes its own node, so a cut opens
    wherever it runs through the mesh (at the end of a cut the point stays whole, as it must).
    Returns (corner_node (T, 3), node_point: the welded id of each node)."""
    tris_w = np.asarray(tris_w)
    T = len(tris_w)
    edge_faces = {}
    for k, t in enumerate(tris_w):
        for u, v in ((t[0], t[1]), (t[1], t[2]), (t[2], t[0])):
            edge_faces.setdefault((min(u, v), max(u, v)), []).append(k)
    cut = set()
    for e, fs in edge_faces.items():
        if len(fs) == 2 and frozenset((int(fgroup[fs[0]]), int(fgroup[fs[1]]))) in pairs:
            cut.add(e)
    corner_node = np.zeros((T, 3), np.int64)
    node_point = []
    around = {}
    for k, t in enumerate(tris_w):
        for j, v in enumerate(t):
            around.setdefault(int(v), []).append((k, j))
    on_cut = set()
    for u, v in cut:
        on_cut.add(int(u))
        on_cut.add(int(v))
    for v, corners in around.items():
        if v not in on_cut:  # a point no cut runs through stays whole, even where two sheets meet at it alone
            nid = len(node_point)
            node_point.append(v)
            for k, j in corners:
                corner_node[k, j] = nid
            continue
        par = {k: k for k, _ in corners}

        def find(a):
            while par[a] != a:
                par[a] = par[par[a]]
                a = par[a]
            return a

        for k, _ in corners:  # join two triangles at v through each uncut edge at v they share
            t = tris_w[k]
            for u in t:
                if u == v:
                    continue
                e = (min(u, v), max(u, v))
                if e in cut:
                    continue
                for k2 in edge_faces.get(e, []):
                    if k2 != k and k2 in par:
                        a, b = find(k), find(k2)
                        if a != b:
                            par[b] = a
        ids = {}
        for k, j in corners:
            r = find(k)
            if r not in ids:
                ids[r] = len(node_point)
                node_point.append(v)
            corner_node[k, j] = ids[r]
    return corner_node, np.array(node_point), len(cut)


def cg_solve(matvec, Bm, diag, x0, iters=3000, tol=1e-7):
    """Jacobi-preconditioned conjugate gradients for an SPD operator, every column of Bm at once."""
    x = x0.copy()
    r = Bm - matvec(x)
    z = r / diag[:, None]
    p = z.copy()
    rz = (r * z).sum(0)
    b0 = np.maximum(np.linalg.norm(Bm, axis=0), 1e-30)
    for it in range(iters):
        Ap = matvec(p)
        a = rz / np.maximum((p * Ap).sum(0), 1e-300)
        x += a[None] * p
        r -= a[None] * Ap
        if (np.linalg.norm(r, axis=0) / b0).max() < tol:
            break
        z = r / diag[:, None]
        rz2 = (r * z).sum(0)
        p = z + (rz2 / np.maximum(rz, 1e-300))[None] * p
        rz = rz2
    return x, it


def harmonic(P, E, L0, anchor_w, anchored, min_len):
    """Weights that are harmonic over the mesh graph (edge weight 1 / rest length, so a weight changes by about the
    same amount per metre everywhere, never across one short edge) and fixed at the anchored points.
    anchor_w: (n, B) weights of the anchored points (others ignored). Points of a part with no anchor keep anchor_w."""
    n, B = anchor_w.shape
    c = 1.0 / np.maximum(L0, min_len)
    free = ~anchored
    deg = np.zeros(n)
    np.add.at(deg, E[:, 0], c)
    np.add.at(deg, E[:, 1], c)

    def lap(X):  # L X over all points
        out = deg[:, None] * X
        np.add.at(out, E[:, 0], -c[:, None] * X[E[:, 1]])
        np.add.at(out, E[:, 1], -c[:, None] * X[E[:, 0]])
        return out

    Xa = np.where(anchored[:, None], anchor_w, 0.0)
    rhs = -lap(Xa)[free]
    fidx = np.nonzero(free)[0]

    def mv(Y):
        Z = np.zeros((n, B))
        Z[fidx] = Y
        return lap(Z)[fidx]

    x, it = cg_solve(mv, rhs, np.maximum(deg[fidx], 1e-12), np.full((len(fidx), B), 1.0 / B))
    W = Xa.copy()
    W[fidx] = np.clip(x, 0.0, None)
    return W, it



# ---------------------------------------------------------------- the warriors: cut, anchor, harmonic weights
# Bone chains of the small humanoid rig. 0: chest, neck, head; 7: hips, spine; 1/2: left/right upper arm; 8/9:
# left/right forearm and hand; 3/4: left/right leg; 5/6: a weapon held rigidly in the left/right hand.
CHAINS = {"hips": 7, "spine": 7, "chest": 0, "neck": 0, "head": 0, "upperarm.L": 1, "forearm.L": 8, "hand.L": 8,
          "upperarm.R": 2, "forearm.R": 9, "hand.R": 9, "thigh.L": 3, "shin.L": 3, "foot.L": 3, "thigh.R": 4,
          "shin.R": 4, "foot.R": 4}
NG = 10
ARM_RADIUS = 0.06  # an arm's points lie within this share of the figure's height of its bones
CLEAR = 0.02  # anchors of two bones that are not jointed keep this share of the figure's height apart (9 mm)
OPEN_GATE = 0.012  # no cut in the mesh may open wider than this share of the figure's height (5 mm on 0.45 m)
_ARMS, _LEGS = (1, 2, 8, 9), (3, 4)
# Chains whose faces must never share an edge: an arm and a leg, the two legs, the two arms, an arm and the lower
# torso (a hand on a belt), a forearm or hand and the chest (a fist on the breastplate), a leg and the upper torso;
# a held weapon and anything but its own forearm and hand.
CUT_PAIRS = ({frozenset((a, b)) for a in _ARMS for b in _LEGS} | {frozenset((3, 4)), frozenset((3, 0)), frozenset((4, 0))}
             | {frozenset((a, b)) for a in (1, 8) for b in (2, 9)} | {frozenset((a, 7)) for a in _ARMS}
             | {frozenset((8, 0)), frozenset((9, 0))}
             | {frozenset((5, g)) for g in range(NG) if g not in (5, 8)}
             | {frozenset((6, g)) for g in range(NG) if g not in (6, 9)})
_SIDE = {1: (1, 8), 8: (1, 8), 2: (2, 9), 9: (2, 9)}
# The cuts made: only a held weapon or shield is cut from the body it touches (it is a separate thing, which leaves
# it). Everything else sculpted together (the legs under a skirt or coat, a hand on a thigh or a belt, an arm against
# the body) stays joined and is blended smoothly, so it can never open a crack; CUT_PAIRS above (every limb from the
# limbs it rests on) opened cracks up to 3 cm wide in the clips and is kept only for comparison.
WEAPON_CUTS = ({frozenset((5, g)) for g in range(NG) if g not in (5, 8)}
               | {frozenset((6, g)) for g in range(NG) if g not in (6, 9)})
CUTS = WEAPON_CUTS


class Humanoid:
    """Weights for one figure cut out of a frieze. The figure is sculpted in one piece, its arms, weapons and legs
    fused to each other, so Blender's heat weights tear it where those parts move apart.

    1. Each point gets a chain from the heat weights (legs never across the midline). A loose part longer than
       6 cm within 3 cm of a hand is a weapon held in that hand (a part over 15 % of the figure only when it is
       long and thin, a full-height spear or halberd); other loose parts take the chain of the body under them.
       Fused weapons and shields are given per vertex (held_by: capsules and boxes in build_warriors.py).
    2. The mesh is cut (vertices doubled in place, no face added or removed) wherever faces of two chains in
       CUT_PAIRS meet, so a hand can leave the thigh it rests on and a weapon the helmet it touches.
    3. Anchors: points in the core of a bone (projecting onto the middle of it, clearly nearer to it than to any
       bone it is not jointed to, every neighbour anchored to the same bone), plus points the heat weights give to
       one bone with confidence; never two anchors of different bones side by side. Held weapons are anchored
       to their hand. Of the settings tried, those that keep at least 85 % of the motion (liveness) and stretch
       least win.
    4. Everything between the anchors is harmonic (see harmonic): the weights blend smoothly across each joint,
       by length, never within one short edge.
    """

    def __init__(self, verts, tris, heat, names, heads, tails, parents, deform, held_by=None, log=print,
                 cuts=CUTS):
        """held_by: optional per-vertex hand bone name ("" for none): a fused shield or weapon held rigidly."""
        self.names = list(names)
        B = len(self.names)
        self.heads, self.tails = np.asarray(heads, float), np.asarray(tails, float)
        self.parents, self.deform = np.asarray(parents), np.asarray(deform, bool)
        idx = {n: i for i, n in enumerate(self.names)}
        self.chain = chain = np.array([CHAINS.get(n, 0) for n in self.names])
        verts = np.asarray(verts, float)
        tris = np.asarray(tris)
        wid = weld_ids(verts)
        self.wid = wid
        nw = int(wid.max()) + 1
        cnt = np.bincount(wid)[:, None]
        Pw = np.zeros((nw, 3))
        np.add.at(Pw, wid, verts)
        Pw /= cnt
        H = np.zeros((nw, B))
        np.add.at(H, wid, np.asarray(heat, float))
        H /= cnt
        H[:, ~self.deform] = 0
        eps = 0.012
        side = np.ones((nw, B), bool)
        side[np.ix_(Pw[:, 0] < -eps, chain == 3)] = False
        side[np.ix_(Pw[:, 0] > eps, chain == 4)] = False
        H = np.where(side, H, 0.0)
        D = np.where(side & self.deform[None], seg_dist(Pw, self.heads, self.tails), np.inf)
        lab = np.where(H.sum(1) < 1e-3, D.argmin(1), H.argmax(1))
        self.arm_relabelled = 0
        # an arm owns only what lies round its bones: the heat weights also hand an arm the coat tail, the belt or
        # the skirt panel its hand rests on, which then tore away with every swing of the arm
        arm_r = ARM_RADIUS * float(Pw[:, 2].max() - Pw[:, 2].min())
        armb = np.isin(chain, list(_ARMS)) & self.deform
        on_arm = np.isin(chain[lab], list(_ARMS))
        if on_arm.any():
            Da = seg_dist(Pw[on_arm], self.heads, self.tails)
            same = np.array([[chain[b] in _SIDE[chain[l]] for b in range(B)] for l in lab[on_arm]]) & armb[None]
            far = np.where(same, Da, np.inf).min(1) > arm_r
            Dn = np.where(armb[None], np.inf, D[on_arm])
            sel = np.nonzero(on_arm)[0][far]
            lab[sel] = Dn[far].argmin(1)
            self.arm_relabelled = int(far.sum())
        held = np.zeros(nw, bool)
        if held_by is not None:
            for v, hn in enumerate(held_by):
                if hn:
                    lab[wid[v]] = idx[hn]
                    held[wid[v]] = True
        tw = wid[tris]
        comp = components(nw, np.concatenate([tw[:, [0, 1]], tw[:, [1, 2]]]))
        hands = [idx["hand.L"], idx["hand.R"]]
        self.parts = []
        cids, csz = np.unique(comp, return_counts=True)
        body = cids[np.argmax(csz)]
        rest = []
        for c in cids:
            pts = np.nonzero(comp == c)[0]
            if c == body:
                continue
            # a large loose part is a body piece (the knight's legs), unless it is long and thin: a full-height
            # spear or halberd, which a hand holds like any small weapon
            sv = np.linalg.svd(Pw[pts] - Pw[pts].mean(0), compute_uv=False)
            thin = sv[1] < 0.25 * sv[0]
            if len(pts) > 0.15 * nw and not thin:
                continue
            ext = float(np.linalg.norm(Pw[pts].max(0) - Pw[pts].min(0)))
            # distance to each hand, measured along the part's edges too: a long shaft (the ji, the spear) has
            # vertices only at its ends, none where the hand closes round it
            inp = np.zeros(nw, bool)
            inp[pts] = True
            pe = np.concatenate([tw[:, [0, 1]], tw[:, [1, 2]], tw[:, [2, 0]]])
            pe = pe[inp[pe[:, 0]] & inp[pe[:, 1]]]
            ts = np.linspace(0.0, 1.0, 9)[:, None, None]
            samp = (Pw[pe[:, 0]][None] * (1 - ts) + Pw[pe[:, 1]][None] * ts).reshape(-1, 3)
            dh = seg_dist(np.concatenate([Pw[pts], samp]), self.heads[hands], self.tails[hands]).min(0)
            j = int(np.argmin(dh))
            # a weapon is long and thin (a sword, a bow, a spear) or large (a shield); a flat skirt panel or tasset
            # hanging by the hand is neither, and stays with the body
            weapon_like = sv[1] < 0.45 * sv[0] or ext >= 0.2
            if dh[j] < 0.03 and ext > 0.06 and weapon_like:
                lab[pts] = hands[j]
                held[pts] = True
                self.parts.append(("held", self.names[hands[j]], len(pts), round(ext, 3)))
            else:
                rest.append(pts)
        for pts in rest:  # other loose parts take the label of the body under them, never a held weapon's
            mp = np.nonzero(~np.isin(np.arange(nw), pts) & ~held)[0]
            for q in np.array_split(pts, max(1, len(pts) // 400)):
                lab[q] = lab[mp[np.argmin(np.linalg.norm(Pw[q][:, None] - Pw[mp][None], axis=2), axis=1)]]
        grp = chain[lab].copy()
        grp[held] = np.where(lab[held] == hands[0], 5, 6)
        fg = np.array([np.bincount(grp[t], minlength=NG).argmax() for t in tw])
        self.tri_group = fg
        cn, npt, self.ncut = fan_split(tw, fg, cuts)
        N = len(npt)
        ng = np.zeros((N, NG))
        np.add.at(ng, cn.ravel(), np.eye(NG)[np.repeat(fg, 3)])
        mixed = (ng > 0).sum(1) > 1
        ng = ng.argmax(1)
        nlab, nheld = lab[npt].copy(), held[npt].copy()
        for k in range(N):
            g = ng[k]
            if g in (5, 6):
                nlab[k] = hands[g - 5]
                nheld[k] = True
            elif chain[nlab[k]] != g and not nheld[k]:
                cand = [i for i in range(B) if self.deform[i] and chain[i] == g]
                nlab[k] = cand[int(np.argmin(seg_dist(Pw[npt[k]][None], self.heads[cand], self.tails[cand])[0]))]
        # the points of the weight solve are the nodes (no further welding)
        self.sk = sk = Skin(Pw[npt], cn, self.deform, labels=np.arange(N), min_len=3e-4)
        sk.names, sk.heads, sk.tails = self.names, self.heads, self.tails
        perm = sk.wid  # node -> point
        self.corner_point = perm[cn]  # (T, 3): the point of each triangle corner
        self.lab = np.zeros(N, np.int64)
        self.lab[perm] = nlab
        self.held = np.zeros(N, bool)
        self.held[perm] = nheld
        self.mixed = np.zeros(N, bool)
        self.mixed[perm] = mixed
        self.Hn = np.zeros((N, B))
        self.Hn[perm] = H[npt]
        self.height = float(Pw[:, 2].max() - Pw[:, 2].min())
        self.contacts = self._contacts(npt, comp, perm, Pw)
        if log:
            log("humanoid: points", nw, "after the cut", N, "cut edges", self.ncut, "parts", self.parts,
                "taken from the arms", self.arm_relabelled)

    def _contacts(self, npt, comp, perm, Pw, touch=1e-3):
        """Pairs of solve points that touch at rest: the two sides of every cut (one point doubled) and points of two
        loose parts within `touch` of each other (a strap on a coat, a plume in a helmet). Moving apart, they open a
        crack in the surface that the edge measure cannot see."""
        pairs, kind = [], []
        first = {}
        for k, p in enumerate(npt):
            if p in first:
                pairs.append((perm[first[p]], perm[k]))
                kind.append(0)
            else:
                first[int(p)] = k
        node_of = np.array([perm[first[p]] if p in first else -1 for p in range(len(Pw))])
        idx = np.nonzero(node_of >= 0)[0]
        for s in range(0, len(idx), 512):
            a = idx[s:s + 512]
            dd = np.linalg.norm(Pw[a][:, None] - Pw[idx][None], axis=2)
            ia, ib = np.nonzero((dd < touch) & (comp[a][:, None] != comp[idx][None]))
            for i, j in zip(a[ia], idx[ib]):
                if i < j:
                    pairs.append((node_of[i], node_of[j]))
                    kind.append(1)
        pairs = np.array(pairs, np.int64).reshape(-1, 2)
        P = self.sk.P
        return pairs, np.linalg.norm(P[pairs[:, 0]] - P[pairs[:, 1]], axis=1), np.array(kind, np.int64)

    def openings(self, W, clips=None, kinds=(0,)):
        """The widest crack each clip opens (metres) along the cuts (kind 0; kind 1: loose parts that touch, which
        may slide apart), where neither side is held by a hand (a held weapon or shield is meant to leave the body it
        rests on). Per clip: (widest, frame, point)."""
        pairs, d0, kind = self.contacts
        keep = ~(self.held[pairs[:, 0]] | self.held[pairs[:, 1]]) & np.isin(kind, kinds)
        pairs, d0 = pairs[keep], d0[keep]
        out = {}
        for name in clips or self.sk.clips:
            if not len(pairs):
                out[name] = (0.0, 0, -1)
                continue
            Pf = self.sk.pose(W, self.sk.clips[name])
            op = np.linalg.norm(Pf[:, pairs[:, 0]] - Pf[:, pairs[:, 1]], axis=2) - d0[None]
            f, k = np.unravel_index(np.argmax(op), op.shape)
            out[name] = (round(float(op[f, k]), 4), int(f), int(pairs[k, 0]))
        return out

    def weights(self, ratio=0.8, margin=0.25, heat_conf=1.0, rings=1):
        sk, names, heads, tails, parents, deform, chain = (self.sk, self.names, self.heads, self.tails, self.parents,
                                                            self.deform, self.chain)
        B, P, N = len(names), sk.P, sk.n
        g = chain[self.lab]
        tor = [i for i in range(B) if deform[i] and chain[i] in (0, 7)]
        allowed = np.zeros((N, B), bool)
        for c in (0, 1, 2, 3, 4, 7, 8, 9):
            if c in (0, 7):
                bones = tor
            elif c in _SIDE:
                bones = [i for i in range(B) if deform[i] and chain[i] in _SIDE[c]] + [names.index("chest")]
            else:
                bones = [i for i in range(B) if deform[i] and chain[i] == c]
            if c in (3, 4):
                bones = bones + [names.index("hips")]
            allowed[np.ix_(g == c, bones)] = True
        D = np.where(allowed, seg_dist(P, heads, tails), np.inf)
        lab = D.argmin(1)
        d1 = D[np.arange(N), lab]
        adj = np.eye(B, dtype=bool)
        for j in range(B):
            if parents[j] >= 0:
                adj[j, parents[j]] = adj[parents[j], j] = True
        d2 = np.where(adj[lab], np.inf, D).min(1)
        ab = tails[lab] - heads[lab]
        t = ((P - heads[lab]) * ab).sum(1) / np.maximum((ab * ab).sum(1), 1e-12)
        hasp = np.array([parents[j] >= 0 and deform[parents[j]] for j in range(B)])
        hask = np.array([any(parents[c] == j and deform[c] for c in range(B)) for j in range(B)])
        lo = np.where(hasp[lab], margin, -np.inf)
        hi = np.where(hask[lab], 1 - margin, np.inf)
        anchored = (t >= lo) & (t <= hi) & (d1 < ratio * d2) & ~self.mixed
        if heat_conf < 1:
            anchored |= (self.Hn.argmax(1) == lab) & (self.Hn.max(1) >= heat_conf) & ~self.mixed
        e0, e1 = sk.E[:, 0], sk.E[:, 1]
        for _ in range(rings):
            diff = (lab[e0] != lab[e1]) | ~anchored[e0] | ~anchored[e1]
            bad = np.zeros(N, bool)
            bad[e0[diff]] = True
            bad[e1[diff]] = True
            anchored &= ~bad
        lab[self.held] = self.lab[self.held]
        anchored |= self.held
        core = (t >= lo) & (t <= hi) & ~self.mixed
        for c in np.unique(sk.comp):  # every bone of a cut-off piece gets anchors there, at least its core
            m = sk.comp == c
            for j in np.unique(lab[m]):
                mj = m & (lab == j)
                if not anchored[mj].any():
                    anchored |= mj & core if (mj & core).any() else mj
        for _ in range(2):  # never two anchors of different bones side by side (a step in the weights)
            clash = anchored[e0] & anchored[e1] & (lab[e0] != lab[e1])
            drop = np.zeros(N, bool)
            drop[e0[clash]] = True
            drop[e1[clash]] = True
            anchored &= ~(drop & ~self.held)
        # nor two anchors of bones that move apart within CLEAR of the figure's height of each other through the
        # air (the inner thighs under a skirt, a forearm on the hip): the blend between them needs room
        clear = CLEAR * self.height
        ai = np.nonzero(anchored & ~self.held)[0]
        drop = np.zeros(N, bool)
        for s0 in range(0, len(ai), 1024):
            a = ai[s0:s0 + 1024]
            dd = np.linalg.norm(P[a][:, None] - P[ai][None], axis=2)
            near = (dd < clear) & ~adj[lab[a]][:, lab[ai]] & (lab[a][:, None] != lab[ai][None])
            drop[a[near.any(1)]] = True
        anchored &= ~drop
        for c in np.unique(sk.comp):  # a piece left with no anchor at all moves with one bone
            m = sk.comp == c
            if not anchored[m].any():
                lab[m] = np.bincount(lab[m]).argmax()
                anchored |= m
        A = np.zeros((N, B))
        A[np.arange(N), lab] = 1.0
        W, _ = harmonic(P, sk.E, sk.L0, A, anchored, 3e-4)
        self.rigid_ref = A
        return limit(W, 4), anchored

    def liveness(self, W):
        """How much of the motion the weights keep: the summed displacement of every point over every clip, with
        these weights, over the same with each point moving rigidly with its nearest bone (1: all of it)."""
        a = b = 0.0
        for M in self.sk.clips.values():
            a += np.linalg.norm(self.sk.pose(W, M) - self.sk.P[None], axis=2).sum()
            b += np.linalg.norm(self.sk.pose(self.rigid_ref, M) - self.sk.P[None], axis=2).sum()
        return a / max(b, 1e-12)

    def fit(self, clip_fn, ladders, gate=2.0, target=1.8, min_live=0.85, log=print, trial_iters=80):
        """clip_fn(amps) -> {clip: deform matrices (frames, bones, 4, 4)}; amps: {clip: amplitude tuple}.
        ladders: {clip: [amplitudes, largest first]}.
        1. The anchor settings are searched and the best weights relaxed (Skin.relax) against every clip at its third
           size.
        2. Clip by clip, each size of its ladder is tried from the largest: the weights are relaxed against it (and
           the other clips as they stand), and the first size at which no edge of that clip stretches past `gate`
           and no cut opens wider than OPEN_GATE of the figure's height (a crack, which the edge measure cannot
           see), while every other clip that passed still passes, is kept with its weights.
        Returns (amps, settings, weights, {clip: (stretch (worst, frame, >1.5, >2), crack (widest, frame, point))})."""
        open_gate = OPEN_GATE * self.height
        amps = {c: lad[min(2, len(lad) - 1)] for c, lad in ladders.items()}

        def load(a):
            self.sk.clips = {}
            for n, M in clip_fn(a).items():
                self.sk.add_clip(n, M)

        def judge(W, a):
            out = {}
            for c in a:
                q = self.sk.edge_q(W, [c])[1][c]
                op = self.openings(W, [c])[c]
                out[c] = (q[0] <= gate and op[0] <= open_gate, q, op)
            return out

        load(amps)
        tries = []
        for ratio in (0.8, 0.6):
            for margin in (0.25, 0.4):
                for hc in (1.0, 0.98, 0.9):
                    W, _ = self.weights(ratio, margin, hc)
                    m = self.sk.measure(W)
                    live = self.liveness(W)
                    tries.append((max(v[0] for v in m.values()), (ratio, margin, hc, round(float(live), 2)), W, live))
        # weights that keep most of the motion (no piece frozen onto one bone), then the least stretch
        tries.sort(key=lambda x: (x[3] < min_live, x[0]))
        first, cfg, W, _ = tries[0]
        W, _, _ = self.sk.relax(W, target, locked=self.held, iters=150)
        res = judge(W, amps)
        if log:
            log(f"humanoid fit: anchors {cfg} -> {first}, relaxed at the third sizes: "
                + ", ".join(f"{c} {v[1][0]}x {v[2][0] * 1000:.1f} mm" for c, v in res.items()))
        for c in sorted(ladders, key=lambda c: -len(ladders[c])):  # the clips with most sizes first
            lad = ladders[c]
            if len(lad) == 1:
                continue
            passed = {k for k, v in res.items() if v[0] and k != c}
            for k, size in enumerate(lad):
                trial = dict(amps, **{c: size})
                load(trial)
                W2, _, _ = self.sk.relax(W, target, locked=self.held, iters=trial_iters)
                r2 = judge(W2, trial)
                if (r2[c][0] and all(r2[p][0] for p in passed)) or k == len(lad) - 1:
                    amps, W, res = trial, W2, r2
                    break
            if log:
                log(f"humanoid {c} at {amps[c]}: " + ", ".join(f"{n} {v[1][0]}x {v[2][0] * 1000:.1f} mm"
                                                            for n, v in res.items()))
        load(amps)
        return amps, cfg, W, {c: (v[1], v[2]) for c, v in res.items()}
