-- PostgreSQL database dump

\restrict 8Gap1uXYa5yiypbtyEju1zSvleJ6Eql9vWhmHebISl14KzIG87FGIghEDCIhEei

-- Dumped from database version 16.15 (Ubuntu 16.15-0ubuntu0.24.04.1)
-- Dumped by pg_dump version 16.15 (Ubuntu 16.15-0ubuntu0.24.04.1)




-- Name: capturas; Type: TABLE; Schema: public; Owner: -

CREATE TABLE public.capturas (
    id integer NOT NULL,
    tramo_id integer NOT NULL,
    archivo_original character varying(255) NOT NULL,
    ruta_imagen character varying(255) NOT NULL,
    ruta_anotada character varying(255) NOT NULL,
    ancho integer NOT NULL,
    alto integer NOT NULL,
    fecha_captura timestamp with time zone NOT NULL,
    origen_fecha character varying(10) NOT NULL,
    lat double precision,
    lon double precision,
    origen_gps character varying(10),
    notas text,
    modelo_version character varying(80) NOT NULL,
    conf_umbral double precision NOT NULL,
    indice_severidad double precision NOT NULL,
    calificacion character varying(12) NOT NULL,
    n_detecciones integer NOT NULL,
    tiempo_inferencia_ms double precision NOT NULL,
    creado_en timestamp with time zone DEFAULT now() NOT NULL,
    perfil character varying(10) DEFAULT 'normal'::character varying NOT NULL,
    parametros text
);


-- Name: capturas_id_seq; Type: SEQUENCE; Schema: public; Owner: -

CREATE SEQUENCE public.capturas_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


-- Name: capturas_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -

ALTER SEQUENCE public.capturas_id_seq OWNED BY public.capturas.id;


-- Name: detecciones; Type: TABLE; Schema: public; Owner: -

CREATE TABLE public.detecciones (
    id integer NOT NULL,
    captura_id integer NOT NULL,
    clase character varying(40) NOT NULL,
    confianza double precision NOT NULL,
    x1 double precision NOT NULL,
    y1 double precision NOT NULL,
    x2 double precision NOT NULL,
    y2 double precision NOT NULL,
    area_frac double precision NOT NULL
);


-- Name: detecciones_id_seq; Type: SEQUENCE; Schema: public; Owner: -

CREATE SEQUENCE public.detecciones_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


-- Name: detecciones_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -

ALTER SEQUENCE public.detecciones_id_seq OWNED BY public.detecciones.id;


-- Name: tramos; Type: TABLE; Schema: public; Owner: -

CREATE TABLE public.tramos (
    id integer NOT NULL,
    nombre character varying(120) NOT NULL,
    descripcion text,
    ciudad character varying(80),
    lat double precision,
    lon double precision,
    creado_en timestamp with time zone DEFAULT now() NOT NULL
);


-- Name: tramos_id_seq; Type: SEQUENCE; Schema: public; Owner: -

CREATE SEQUENCE public.tramos_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


-- Name: tramos_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -

ALTER SEQUENCE public.tramos_id_seq OWNED BY public.tramos.id;


-- Name: video_frames; Type: TABLE; Schema: public; Owner: -

CREATE TABLE public.video_frames (
    id integer NOT NULL,
    video_id integer NOT NULL,
    t_seg double precision NOT NULL,
    indice double precision NOT NULL,
    n_detecciones integer NOT NULL,
    conteo text NOT NULL,
    ruta_imagen character varying(255),
    lat double precision,
    lon double precision
);


-- Name: video_frames_id_seq; Type: SEQUENCE; Schema: public; Owner: -

CREATE SEQUENCE public.video_frames_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


-- Name: video_frames_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -

ALTER SEQUENCE public.video_frames_id_seq OWNED BY public.video_frames.id;


-- Name: video_hallazgos; Type: TABLE; Schema: public; Owner: -

CREATE TABLE public.video_hallazgos (
    id integer NOT NULL,
    video_id integer NOT NULL,
    clase character varying(32) NOT NULL,
    t_ini double precision NOT NULL,
    t_fin double precision NOT NULL,
    n_apariciones integer NOT NULL,
    conf_max double precision NOT NULL,
    area_max double precision NOT NULL,
    ruta_imagen character varying(255) NOT NULL,
    lat double precision,
    lon double precision,
    descartado boolean DEFAULT false NOT NULL
);


-- Name: video_hallazgos_id_seq; Type: SEQUENCE; Schema: public; Owner: -

CREATE SEQUENCE public.video_hallazgos_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


-- Name: video_hallazgos_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -

ALTER SEQUENCE public.video_hallazgos_id_seq OWNED BY public.video_hallazgos.id;


-- Name: videos; Type: TABLE; Schema: public; Owner: -

CREATE TABLE public.videos (
    id integer NOT NULL,
    tramo_id integer NOT NULL,
    archivo_original character varying(255) NOT NULL,
    fecha_inicio timestamp with time zone NOT NULL,
    origen_fecha character varying(10) NOT NULL,
    duracion_s double precision,
    fps double precision,
    ancho integer NOT NULL,
    alto integer NOT NULL,
    intervalo_s double precision NOT NULL,
    n_frames integer NOT NULL,
    indice_medio double precision NOT NULL,
    indice_max double precision NOT NULL,
    pct_afectados double precision NOT NULL,
    calificacion character varying(12) NOT NULL,
    perfil character varying(10) NOT NULL,
    parametros text,
    modo character varying(12) DEFAULT 'fotogramas'::character varying NOT NULL,
    cada_n integer,
    ruta_anotado character varying(255),
    modelo_version character varying(80) NOT NULL,
    tiempo_proceso_s double precision NOT NULL,
    notas text,
    creado_en timestamp with time zone DEFAULT now() NOT NULL,
    ruta_gps text
);


-- Name: videos_id_seq; Type: SEQUENCE; Schema: public; Owner: -

CREATE SEQUENCE public.videos_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


-- Name: videos_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -

ALTER SEQUENCE public.videos_id_seq OWNED BY public.videos.id;


-- Name: capturas id; Type: DEFAULT; Schema: public; Owner: -

ALTER TABLE ONLY public.capturas ALTER COLUMN id SET DEFAULT nextval('public.capturas_id_seq'::regclass);


-- Name: detecciones id; Type: DEFAULT; Schema: public; Owner: -

ALTER TABLE ONLY public.detecciones ALTER COLUMN id SET DEFAULT nextval('public.detecciones_id_seq'::regclass);


-- Name: tramos id; Type: DEFAULT; Schema: public; Owner: -

ALTER TABLE ONLY public.tramos ALTER COLUMN id SET DEFAULT nextval('public.tramos_id_seq'::regclass);


-- Name: video_frames id; Type: DEFAULT; Schema: public; Owner: -

ALTER TABLE ONLY public.video_frames ALTER COLUMN id SET DEFAULT nextval('public.video_frames_id_seq'::regclass);


-- Name: video_hallazgos id; Type: DEFAULT; Schema: public; Owner: -

ALTER TABLE ONLY public.video_hallazgos ALTER COLUMN id SET DEFAULT nextval('public.video_hallazgos_id_seq'::regclass);


-- Name: videos id; Type: DEFAULT; Schema: public; Owner: -

ALTER TABLE ONLY public.videos ALTER COLUMN id SET DEFAULT nextval('public.videos_id_seq'::regclass);


-- Name: capturas capturas_pkey; Type: CONSTRAINT; Schema: public; Owner: -

ALTER TABLE ONLY public.capturas
    ADD CONSTRAINT capturas_pkey PRIMARY KEY (id);


-- Name: detecciones detecciones_pkey; Type: CONSTRAINT; Schema: public; Owner: -

ALTER TABLE ONLY public.detecciones
    ADD CONSTRAINT detecciones_pkey PRIMARY KEY (id);


-- Name: tramos tramos_nombre_key; Type: CONSTRAINT; Schema: public; Owner: -

ALTER TABLE ONLY public.tramos
    ADD CONSTRAINT tramos_nombre_key UNIQUE (nombre);


-- Name: tramos tramos_pkey; Type: CONSTRAINT; Schema: public; Owner: -

ALTER TABLE ONLY public.tramos
    ADD CONSTRAINT tramos_pkey PRIMARY KEY (id);


-- Name: video_frames video_frames_pkey; Type: CONSTRAINT; Schema: public; Owner: -

ALTER TABLE ONLY public.video_frames
    ADD CONSTRAINT video_frames_pkey PRIMARY KEY (id);


-- Name: video_hallazgos video_hallazgos_pkey; Type: CONSTRAINT; Schema: public; Owner: -

ALTER TABLE ONLY public.video_hallazgos
    ADD CONSTRAINT video_hallazgos_pkey PRIMARY KEY (id);


-- Name: videos videos_pkey; Type: CONSTRAINT; Schema: public; Owner: -

ALTER TABLE ONLY public.videos
    ADD CONSTRAINT videos_pkey PRIMARY KEY (id);


-- Name: ix_capturas_tramo_fecha; Type: INDEX; Schema: public; Owner: -

CREATE INDEX ix_capturas_tramo_fecha ON public.capturas USING btree (tramo_id, fecha_captura);


-- Name: ix_detecciones_captura_id; Type: INDEX; Schema: public; Owner: -

CREATE INDEX ix_detecciones_captura_id ON public.detecciones USING btree (captura_id);


-- Name: ix_video_frames_video_id; Type: INDEX; Schema: public; Owner: -

CREATE INDEX ix_video_frames_video_id ON public.video_frames USING btree (video_id);


-- Name: ix_video_hallazgos_video_id; Type: INDEX; Schema: public; Owner: -

CREATE INDEX ix_video_hallazgos_video_id ON public.video_hallazgos USING btree (video_id);


-- Name: ix_videos_tramo_fecha; Type: INDEX; Schema: public; Owner: -

CREATE INDEX ix_videos_tramo_fecha ON public.videos USING btree (tramo_id, fecha_inicio);


-- Name: capturas capturas_tramo_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -

ALTER TABLE ONLY public.capturas
    ADD CONSTRAINT capturas_tramo_id_fkey FOREIGN KEY (tramo_id) REFERENCES public.tramos(id) ON DELETE CASCADE;


-- Name: detecciones detecciones_captura_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -

ALTER TABLE ONLY public.detecciones
    ADD CONSTRAINT detecciones_captura_id_fkey FOREIGN KEY (captura_id) REFERENCES public.capturas(id) ON DELETE CASCADE;


-- Name: video_frames video_frames_video_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -

ALTER TABLE ONLY public.video_frames
    ADD CONSTRAINT video_frames_video_id_fkey FOREIGN KEY (video_id) REFERENCES public.videos(id) ON DELETE CASCADE;


-- Name: video_hallazgos video_hallazgos_video_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -

ALTER TABLE ONLY public.video_hallazgos
    ADD CONSTRAINT video_hallazgos_video_id_fkey FOREIGN KEY (video_id) REFERENCES public.videos(id) ON DELETE CASCADE;


-- Name: videos videos_tramo_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -

ALTER TABLE ONLY public.videos
    ADD CONSTRAINT videos_tramo_id_fkey FOREIGN KEY (tramo_id) REFERENCES public.tramos(id) ON DELETE CASCADE;


-- PostgreSQL database dump complete

\unrestrict 8Gap1uXYa5yiypbtyEju1zSvleJ6Eql9vWhmHebISl14KzIG87FGIghEDCIhEei

