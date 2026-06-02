export type Role = 'OBSERVER' | 'OPERATOR' | 'ADMIN' | 'SUPER_ADMIN';

export type Permission = 
  | 'read:prices' 
  | 'read:market' 
  | 'write:oracle' 
  | 'read:config' 
  | 'write:config'
  | '*';