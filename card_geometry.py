"""Conservative visible card quadrilaterals, independently of detector OBBs.

Contours are proposals, not a learned corner detector. Missing/occluded edges
must remain unresolved; never manufacture a precise OCR crop from the OBB.
"""
import cv2
import numpy as np
from itertools import product


def visible_quads(image):
    scale=min(1.,1280/max(image.shape[:2]))
    small=cv2.resize(image,None,fx=scale,fy=scale) if scale<1 else image
    gray=cv2.cvtColor(small,cv2.COLOR_BGR2GRAY)
    gray=cv2.GaussianBlur(gray,(3,3),0)
    proposals=[]
    for low,high in ((35,100),(70,180)):
        edges=cv2.Canny(gray,low,high)
        contours,_=cv2.findContours(edges,cv2.RETR_LIST,cv2.CHAIN_APPROX_SIMPLE)
        for contour in contours:
            area=abs(cv2.contourArea(contour))
            if area<1000*scale*scale:continue
            perimeter=cv2.arcLength(contour,True)
            quad=cv2.approxPolyDP(contour,.018*perimeter,True).reshape(-1,2)
            if len(quad)!=4 or not cv2.isContourConvex(quad):continue
            quad=quad.astype(np.float32)/scale
            # A closed rectangle at the image boundary is not evidence of a card edge.
            h,w=image.shape[:2]
            if (quad[:,0]<3).any() or (quad[:,0]>w-4).any() or (quad[:,1]<3).any() or (quad[:,1]>h-4).any():continue
            qa=abs(cv2.contourArea(quad))
            if abs(area/scale**2-qa)/qa>.08:continue
            if cv2.contourArea(quad,oriented=True)<0:quad=quad[::-1].copy()
            if any(np.linalg.norm(quad.mean(0)-q.mean(0))<3 and abs(qa/cv2.contourArea(q)-1)<.03 for q in proposals):continue
            proposals.append(quad)
    return proposals


def visible_lines(image):
    scale=min(1.,1280/max(image.shape[:2]))
    small=cv2.resize(image,None,fx=scale,fy=scale) if scale<1 else image
    gray=cv2.cvtColor(small,cv2.COLOR_BGR2GRAY)
    lines=cv2.createLineSegmentDetector().detect(gray)[0]
    return np.empty((0,2,2),np.float32) if lines is None else lines.reshape(-1,2,2)/scale


def line_quads(corners,lines,image_shape,per_side=3,min_overlap=None):
    """Intersect four observed long edges near an OBB, retaining perspective.

    `min_overlap` replaces the end-position rule by a minimum overlap with the
    box side, for boxes that may be much larger than the card they contain.
    """
    p=np.float32(corners);groups=[]
    if len(lines)==0:return []
    delta=lines[:,1]-lines[:,0];sizes=np.linalg.norm(delta,axis=1)
    directions=delta/np.maximum(sizes[:,None],1e-6)
    for i in range(4):
        a,b=p[i],p[(i+1)%4];edge=b-a;length=np.linalg.norm(edge)
        unit=edge/length;normal=np.array([-unit[1],unit[0]])
        depth=np.linalg.norm(p[(i+2)%4]-b)
        position=((lines-a)@unit)/length
        inward=((lines-a)@normal)/depth
        mask=(sizes>=.50*length)&(np.abs(directions@unit)>=.965)
        if min_overlap is None:mask&=(position.max(1)>=.65)&(position.min(1)<=.35)
        else:mask&=(np.minimum(position.max(1),1)-np.maximum(position.min(1),0))>=min_overlap
        mask&=(position.min(1)>=-.25)&(position.max(1)<=1.25)
        mask&=(inward.min(1)>=-.13)&(inward.max(1)<=.38)
        indices=np.flatnonzero(mask)
        if len(indices)==0:return []
        groups.append(lines[indices[np.argsort(sizes[indices])[-per_side:]]])
    quads=[];h,w=image_shape[:2]
    for edges in product(*groups):
        points=[]
        for i in range(4):
            a,b=edges[i-1];c,d=edges[i]
            matrix=np.column_stack((b-a,c-d))
            if abs(np.linalg.det(matrix))<1:break
            t=np.linalg.solve(matrix,c-a)[0];points.append(a+t*(b-a))
        if len(points)!=4:continue
        q=np.float32(points)
        if not cv2.isContourConvex(q) or cv2.contourArea(q,oriented=True)<=0:continue
        if (q[:,0]<3).any() or (q[:,0]>w-4).any() or (q[:,1]<3).any() or (q[:,1]>h-4).any():continue
        supported=True
        for i,line in enumerate(edges):
            edge=q[(i+1)%4]-q[i];length=np.linalg.norm(edge)
            positions=((line-q[i])@edge)/(length*length)
            # A long supporting segment must cover most of the inferred side;
            # this rejects large extrapolations through occluding cards.
            coverage=max(0,min(1,positions.max())-max(0,positions.min()))
            if coverage<.72:supported=False;break
        if supported:quads.append(q)
    return quads


def edge_channels(image):
    """Lab channels: a silver foil border on light wood is invisible in luminance
    but separates clearly in b* (blue-yellow); a* and L cover other borders."""
    return list(cv2.split(cv2.cvtColor(image,cv2.COLOR_BGR2LAB)))


def line_fit(x,y):
    """Least-squares slope and intercept, as np.polyfit(x,y,1) without its overhead."""
    mx=x.mean();my=y.mean();dx=x-mx
    slope=float((dx*(y-my)).sum()/max((dx*dx).sum(),1e-9))
    return np.array([slope,my-slope*mx])


def snapped_segments(channels,corners,step=4,angle_cos=.965,min_gradient=8.,inlier_px=2.5,min_columns=.72,per_side=5,reach=2,max_gap=3,max_candidates=10,trace=None):
    """Long observed edge segments near each OBB side, rebuilt from gradient maxima.

    The line detector fragments low-contrast card borders (foil on light wood)
    into pieces far shorter than the side, so `line_quads` never sees a segment
    covering half the side. Here every side gets a band sampled along the box
    edge in each channel; gradient maxima across the band vote for lines that
    stay within the same angle tolerance as `line_quads`, and each fitted line
    becomes one segment bounded by its extreme supporting columns. Support must
    be dense inside that extent and keep one channel and contrast polarity, so a
    segment is still observed evidence, not an extrapolation; `line_quads` keeps
    applying its own coverage rule.
    """
    p=np.float32(corners);h,w=channels[0].shape[:2];segments=[]
    for i in range(4):
        a,b=p[i],p[(i+1)%4];length=float(np.linalg.norm(b-a))
        if length<20:continue
        unit=(b-a)/length;normal=np.array([-unit[1],unit[0]],np.float32)
        depth=float(np.linalg.norm(p[(i+2)%4]-b))
        if np.dot(p[(i+2)%4]-b,normal)<0:normal=-normal
        # Same band as the line filters: slightly outside, up to 38% inside.
        s=np.arange(-.13*depth,.38*depth,1.,np.float32)
        t=np.arange(-.20*length,1.20*length,step,np.float32)
        xs=a[0]+t[None,:]*unit[0]+s[:,None]*normal[0];ys=a[1]+t[None,:]*unit[1]+s[:,None]*normal[1]
        if len(t)<12 or len(s)<12:continue
        # Signed derivative of Gaussian across the band per channel, scaled so a
        # clean unit step answers 1: a border blurred over several pixels keeps
        # its full contrast and still produces one peak at the border centre.
        offsets=np.arange(-3*reach,3*reach+1,dtype=np.float32);weights=offsets*np.exp(-offsets**2/(2.*reach*reach))
        kernel=(weights/weights[offsets>0].sum()).astype(np.float32)[:,None]
        gradients=[]
        for channel in channels:
            band=cv2.remap(channel,xs,ys,cv2.INTER_LINEAR,borderMode=cv2.BORDER_REPLICATE)
            band=cv2.blur(band,(3,1)).astype(np.float32)
            gradients.append(cv2.filter2D(band,cv2.CV_32F,kernel,borderType=cv2.BORDER_REPLICATE))
        # Peaks per channel against that channel's own noise floor, so a clean
        # chroma border is not drowned by luminance texture elsewhere in the band.
        rows,cols,polarity=[],[],[]
        for index,gradient in enumerate(gradients):
            magnitude=np.abs(gradient)
            threshold=max(min_gradient,3*float(np.median(magnitude)))
            peaks=(magnitude[1:-1]>=magnitude[:-2])&(magnitude[1:-1]>magnitude[2:])&(magnitude[1:-1]>=threshold)
            r,c=np.nonzero(peaks);r=r+1
            rows.append(r);cols.append(c);polarity.append(index*2+(gradient[r,c]>0))
        rows=np.concatenate(rows);cols=np.concatenate(cols);polarity=np.concatenate(polarity)
        outside=(xs[rows,cols]<0)|(xs[rows,cols]>w-1)|(ys[rows,cols]<0)|(ys[rows,cols]>h-1)
        rows,cols,polarity=rows[~outside],cols[~outside],polarity[~outside]
        side_trace={'side':i,'peaks':int(len(rows)),'lines':[]}
        if trace is not None:
            side_trace['points']=(t[cols],s[rows],polarity,length,depth);trace.append(side_trace)
        if len(rows)<12:continue
        pts_t=t[cols];pts_s=s[rows];column_index=cols
        # Deterministic vote over (signature, slope, offset): a weak border only
        # needs consistent peaks along the side, not lucky random pairs. The
        # strongest cells across all signatures are verified, few at a time.
        max_slope=np.tan(np.arccos(angle_cos));slopes=np.linspace(-max_slope,max_slope,int(round(2*max_slope/.015))+1)
        mid=.5*length;candidates=[]
        signatures,sig_index=np.unique(polarity,return_inverse=True)
        offsets=np.rint(pts_s[:,None]-slopes[None,:]*(pts_t[:,None]-mid)-s[0]).astype(int)
        valid=(offsets>=0)&(offsets<len(s))
        cell=(sig_index[:,None]*len(slopes)+np.arange(len(slopes))[None,:])*len(s)+offsets
        votes=np.bincount(cell[valid],minlength=len(signatures)*len(slopes)*len(s)).reshape(len(signatures),len(slopes),len(s)).astype(np.float32)
        # Tolerate one pixel of peak jitter along the band.
        votes[:,:,1:-1]+=votes[:,:,:-2]+votes[:,:,2:]
        members=[np.flatnonzero(sig_index==k) for k in range(len(signatures))]
        for _ in range(max_candidates):
            flat=int(np.argmax(votes));k,rest=divmod(flat,len(slopes)*len(s));bi,oi=divmod(rest,len(s))
            if votes[k,bi,oi]<8:break
            votes[k,max(0,bi-3):bi+4,max(0,oi-3):oi+4]=0
            sel=members[k];T=pts_t[sel];S=pts_s[sel]
            slope=slopes[bi];offset=s[0]+oi
            inliers=sel[np.abs(S-(slope*(T-mid)+offset))<=inlier_px]
            if len(inliers)<8:continue
            # The vote grid is coarse; a least-squares refit lets one long
            # border collect the support that slope quantisation had split.
            fit=line_fit(pts_t[inliers],pts_s[inliers])
            inliers=sel[np.abs(S-(fit[0]*T+fit[1]))<=inlier_px]
            columns=np.unique(column_index[inliers])
            if len(columns)<8:continue
            # Collinear texture beyond the card also votes: keep only the
            # longest run of support without gaps above `max_gap` columns,
            # as a line detector ends its segment where the edge stops.
            breaks=np.flatnonzero(np.diff(columns)>max_gap)
            starts=np.r_[0,breaks+1];stops=np.r_[breaks,len(columns)-1]
            run=int(np.argmax(columns[stops]-columns[starts]))
            columns=columns[starts[run]:stops[run]+1]
            inliers=inliers[(column_index[inliers]>=columns[0])&(column_index[inliers]<=columns[-1])]
            if len(columns)<8:continue
            extent=float(columns.max()-columns.min())*step;density=len(columns)/(extent/step+1)
            candidates.append((len(columns)*density,int(signatures[k]),inliers,columns,extent,density))
        taken=[]
        for score,signature,inliers,columns,extent,density in sorted(candidates,key=lambda c:-c[0]):
            if len(taken)>=per_side:break
            fit=line_fit(pts_t[inliers],pts_s[inliers])
            side_trace['lines'].append({'signature':signature,'columns':int(len(columns)),'extent':round(extent/length,2),
                'density':round(density,2),'offset':round(float(np.mean(pts_s[inliers]))/depth,3)})
            if extent<.25*length or density<min_columns:continue
            # The same physical edge may vote in two channels; keep one segment.
            if any(abs((fit[0]-other[0])*mid+fit[1]-other[1])<3 and abs(fit[0]-other[0])<.02 for other in taken):continue
            taken.append(fit)
            # Express the fitted line as a segment bounded by its supported columns.
            ends=[a+tt*unit+(fit[0]*tt+fit[1])*normal for tt in (t[columns.min()],t[columns.max()])]
            segments.append(np.float32(ends))
    return np.float32(segments).reshape(-1,2,2) if segments else np.empty((0,2,2),np.float32)


def refine_corners(corners,proposals):
    original=np.asarray(corners,dtype=np.float32)
    if original.shape!=(4,2) or not np.isfinite(original).all() or not cv2.isContourConvex(original):return None
    area=abs(cv2.contourArea(original))
    if area<400:return None
    candidates=[]
    for quad in proposals:
        ratio=cv2.contourArea(quad)/area
        if not .45<ratio<1.25:continue
        intersection=cv2.intersectConvexConvex(original,quad)[0]
        iou=intersection/(area+cv2.contourArea(quad)-intersection)
        if iou<.48:continue
        aligned=min((np.roll(quad,k,axis=0) for k in range(4)),key=lambda q:float(np.linalg.norm(q-original,axis=1).sum()))
        lengths=np.linalg.norm(np.roll(aligned,-1,axis=0)-aligned,axis=1)
        aspect=(lengths[0]+lengths[2])/(lengths[1]+lengths[3])
        if not .55<aspect<.80:continue
        displacement=np.linalg.norm(aligned-original,axis=1)/max(np.linalg.norm(original[0]-original[2]),1)
        if displacement.max()>.35:continue
        candidates.append((float(cv2.contourArea(quad)),aligned,iou))
    if not candidates:return None
    # The outer border contains text. Choosing the strongest inner artwork or
    # text frame instead would silently move both anatomical strips.
    _,quad,iou=max(candidates,key=lambda c:c[0])
    return {'corners':quad.tolist(),'geometry_status':'contour_refined','geometry_iou':round(float(iou),3)}


class GeometryRefiner:
    """Extract evidence once per frame, share it across all detected cards."""
    def __init__(self,image,snap_edges=True):
        self.shape=image.shape
        self.quads=visible_quads(image)
        self.lines=visible_lines(image)
        self.channels=edge_channels(image) if snap_edges else None

    def refine(self,corners):
        p=np.float32(corners);h,w=self.shape[:2]
        if p.shape!=(4,2) or not np.isfinite(p).all() or not cv2.isContourConvex(p):
            return {'geometry_status':'invalid'}
        # Near the frame boundary an inner illustration can look like a whole
        # card. Allow only a small correction backed by a complete contour.
        margin=max(4,min(h,w)*.012)
        if (p[:,0]<margin).any() or (p[:,0]>w-margin).any() or (p[:,1]<margin).any() or (p[:,1]>h-margin).any():
            complete=[q for q in self.quads if cv2.contourArea(q)>.80*abs(cv2.contourArea(p))]
            result=refine_corners(p,complete)
            if result:return {**result,'geometry_source':'contours_lines'}
            return {'geometry_status':'frame_edge'}
        result=refine_corners(p,self.quads+line_quads(p,self.lines,self.shape))
        if result:result['geometry_source']='contours_lines'
        elif self.channels is not None:
            # Only for boxes the contour and line detectors could not resolve.
            snapped=snapped_segments(self.channels,p)
            if len(snapped):
                # Inner frames also produce long segments; give the outer border a
                # seat and let refine_corners keep its largest-area preference.
                result=refine_corners(p,line_quads(p,np.concatenate((self.lines,snapped)),self.shape,per_side=4,min_overlap=.35))
                # Same contract for consumers (OCR crops, viewer); the source stays auditable.
                if result:result['geometry_source']='snapped_edges'
        return result or {'geometry_status':'unresolved'}
