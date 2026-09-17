// @hono/swagger-ui는 CDN 자산만 사용하므로 실행 패키지 없이 타입만 최소 정의한다.
declare module 'swagger-ui-dist' {
  export type SwaggerConfigs = {
    [key: string]: unknown;
    configUrl?: string;
    deepLinking?: boolean;
    spec?: unknown;
    url?: string;
    urls?: Array<{ url: string; name: string }>;
    layout?: string;
    docExpansion?: string;
    validatorUrl?: string | false;
  };
}
